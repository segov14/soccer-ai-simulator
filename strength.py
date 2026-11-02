"""Season-only opponent-adjusted football goal ratings.

Data input is match scores from football-data.org. This is NOT observed xG,
not an independently calibrated betting model, and not a promise of accuracy.

A weighted Poisson likelihood learns attack and defense simultaneously across
several competitions. Shared clubs in UCL and their domestic leagues bridge
otherwise disconnected competition strengths. Ridge shrinkage prevents small
samples from producing excessively large ratings; unavailable domestic leagues
remain a visible source of uncertainty.
"""
from collections import Counter
from datetime import datetime, timezone
import math

import numpy as np

DOMESTIC = {
    'PD': 'La Liga', 'PL': 'Premier League', 'BL1': 'Bundesliga',
    'SA': 'Serie A', 'FL1': 'Ligue 1', 'PPL': 'Primeira Liga', 'DED': 'Eredivisie',
}
COMPETITIONS = {'CL': 'Champions League', **DOMESTIC}
# These competitions are advertised as free-access by football-data.org.
# Check what the user's specific token allows; gracefully omit restricted feeds.
DATA_SOURCES = ['CL', 'PD', 'PL', 'BL1', 'SA', 'FL1', 'PPL', 'DED']
PRIOR_TEAM_GAMES = 9.0
RECENCY_HALF_LIFE_DAYS = 75.0
PRIOR_GOALS_PER_TEAM = 1.35


def _parsedate(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, AttributeError):
        return None


def collect_results(results_by_comp, as_of=None):
    """Collect only valid completed match scores strictly before as_of (if any)."""
    cutoff = _parsedate(as_of) if as_of else None
    rows = []
    used = set()
    for competition, games in results_by_comp.items():
        if competition not in COMPETITIONS:
            continue
        for game in games:
            h, a = game.get('hid'), game.get('aid')
            hg, ag = game.get('hg'), game.get('ag')
            kickoff = _parsedate(game.get('date_utc'))
            if h is None or a is None or h == a or kickoff is None:
                continue
            if cutoff and kickoff >= cutoff:
                continue
            if any(isinstance(x, bool) or not isinstance(x, int) or x < 0 for x in (hg, ag)):
                continue
            identifier = (competition, game.get('id') or (str(h), str(a), kickoff.isoformat()))
            if identifier in used:
                continue
            used.add(identifier)
            rows.append({'code': competition, 'home': str(h), 'away': str(a),
                         'hg': hg, 'ag': ag, 'date': kickoff})
    return sorted(rows, key=lambda r: r['date'])


def fit_strength(results_by_comp, as_of=None, max_steps=90):
    """Regularized weighted Poisson goal model with transparent sample counts.

    No pre-match prediction uses the result of the selected fixture. For the
    historical backtest, ``as_of`` excludes future and same-day outcomes.
    """
    matches = collect_results(results_by_comp, as_of=as_of)
    if not matches:
        return {'teams': {}, 'base': {'CL': PRIOR_GOALS_PER_TEAM},
                'home_ratio': 1.20, 'n_matches': 0, 'codes': [], 'as_of': as_of}

    now = _parsedate(as_of) if as_of else datetime.now(timezone.utc)
    teams = sorted({r['home'] for r in matches} | {r['away'] for r in matches})
    ti = {t: i for i, t in enumerate(teams)}
    codes = sorted({r['code'] for r in matches})
    ci = {c: i for i, c in enumerate(codes)}
    hi = np.array([ti[m['home']] for m in matches], dtype=int)
    ai = np.array([ti[m['away']] for m in matches], dtype=int)
    co = np.array([ci[m['code']] for m in matches], dtype=int)
    hg = np.array([m['hg'] for m in matches], dtype=float)
    ag = np.array([m['ag'] for m in matches], dtype=float)
    day_age = np.array([max((now - m['date']).total_seconds() / 86400, 0) for m in matches])
    w = np.exp2(-day_age / RECENCY_HALF_LIFE_DAYS)

    # Data-led competition goal environments, shrunk to a global 1.35 prior.
    base = {}
    for code in codes:
        mask = (co == ci[code])
        count = float(w[mask].sum())
        mean = (float((w[mask] * (hg[mask] + ag[mask])).sum()) + 30 * 2 * PRIOR_GOALS_PER_TEAM) / (2 * count + 60)
        base[code] = max(0.8, min(2.15, mean))
    baseline = np.array([math.log(base[m['code']]) for m in matches])

    # Ratio of home to away goals, with a proper prior from 100 pseudo goals.
    home_ratio = (float((w * hg).sum()) + 55 * math.sqrt(1.20)) / (float((w * ag).sum()) + 55 / math.sqrt(1.20))
    home_ratio = float(np.clip(home_ratio, 1.04, 1.48))
    home_offset = math.log(home_ratio) / 2

    atk = np.zeros(len(teams), dtype=float)
    conceded = np.zeros(len(teams), dtype=float)
    # Coordinate-like damped Newton updates to a ridge-regularized Poisson GLM.
    # A stronger prior represents 9 pseudo games of neutral performance.
    prior = float(PRIOR_TEAM_GAMES * PRIOR_GOALS_PER_TEAM)
    for _ in range(max_steps):
        home_log = np.clip(baseline + home_offset + atk[hi] + conceded[ai], -2.3, 1.8)
        away_log = np.clip(baseline - home_offset + atk[ai] + conceded[hi], -2.3, 1.8)
        home_mu = np.exp(home_log)
        away_mu = np.exp(away_log)
        gh = w * (hg - home_mu)
        ga = w * (ag - away_mu)
        attack_g = -prior * atk
        defend_g = -prior * conceded
        attack_h = np.full(len(teams), prior)
        defend_h = np.full(len(teams), prior)
        np.add.at(attack_g, hi, gh)
        np.add.at(attack_g, ai, ga)
        np.add.at(defend_g, ai, gh)
        np.add.at(defend_g, hi, ga)
        np.add.at(attack_h, hi, w * home_mu)
        np.add.at(attack_h, ai, w * away_mu)
        np.add.at(defend_h, ai, w * home_mu)
        np.add.at(defend_h, hi, w * away_mu)
        delta_attack = 0.38 * attack_g / attack_h
        delta_defend = 0.38 * defend_g / defend_h
        atk = np.clip(atk + delta_attack, -0.9, 0.9)
        conceded = np.clip(conceded + delta_defend, -0.9, 0.9)
        if max(float(np.max(np.abs(delta_attack))), float(np.max(np.abs(delta_defend)))) < 1e-6:
            break

    totals = {t: Counter() for t in teams}
    latest = {t: None for t in teams}
    for m in matches:
        for t in (m['home'], m['away']):
            totals[t]['matches'] += 1
            totals[t][m['code']] += 1
            latest[t] = m['date']
    out = {}
    for t in teams:
        j = ti[t]
        comps = {c: totals[t][c] for c in codes if totals[t][c]}
        out[t] = {
            'attack': float(np.exp(atk[j])), 'defense_conceded': float(np.exp(conceded[j])),
            'games': totals[t]['matches'], 'domestic_games': sum(totals[t][c] for c in DOMESTIC),
            'ucl_games': totals[t]['CL'], 'by_competition': comps,
            'last_played': latest[t].date().isoformat() if latest[t] else None,
        }
    return {'teams': out, 'base': base, 'home_ratio': home_ratio,
            'n_matches': len(matches), 'codes': codes, 'as_of': as_of}


def project_goals(fitted, home_id, away_id, competition='CL', neutral=False):
    """Predict Poisson goal means, giving data quality for each team.

    Multipliers learned from domestic+UCL opponents; no fabricated xG or stats.
    """
    h = fitted['teams'].get(str(home_id))
    a = fitted['teams'].get(str(away_id))
    h_attack = h['attack'] if h else 1.0
    a_attack = a['attack'] if a else 1.0
    h_weakness = h['defense_conceded'] if h else 1.0
    a_weakness = a['defense_conceded'] if a else 1.0
    base = fitted['base'].get(competition, PRIOR_GOALS_PER_TEAM)
    venue = 1 if neutral else math.sqrt(fitted['home_ratio'])
    hm = float(np.clip(base * h_attack * a_weakness * venue, 0.15, 4.2))
    am = float(np.clip(base * a_attack * h_weakness / venue, 0.15, 4.2))

    def quality(stats):
        if not stats:
            return 'Unavailable — league-average prior'
        if stats['games'] < 4:
            return 'Very limited — fewer than 4 matches'
        if stats['domestic_games'] == 0 and competition == 'CL':
            return 'Limited — European matches only (domestic league unavailable)'
        if stats['games'] < 9:
            return 'Limited — fewer than 9 matches'
        return 'Season results available — unvalidated model'

    return {'home_goals': hm, 'away_goals': am,
            'home_rating': h, 'away_rating': a,
            'home_quality': quality(h), 'away_quality': quality(a),
            'base': base, 'venue_multiplier': venue,
            'n_matches': fitted['n_matches']}


def compare_backtest(results_by_comp, target_comp, limit=40, min_prior=30):
    """Evaluate old vs new predictions on identical fixtures strictly out of sample.

    Both models see only matches earlier than the evaluated *calendar day*.
    Diagnostic, may show worse new performance. NOT model calibration.
    """
    from advanced import exact_markets
    from model import rating_from_results, expected_goals

    if target_comp not in results_by_comp:
        return []
    games = sorted(results_by_comp[target_comp], key=lambda x: x.get('date_utc', ''))
    output = []
    for match in games[-limit:]:
        d = str(match.get('date_utc', ''))[:10]
        if len(d) != 10 or not all(k in match for k in ('hg', 'ag', 'hid', 'aid')):
            continue
        prior_all = {c: [m for m in ms if str(m.get('date_utc', ''))[:10] < d]
                     for c, ms in results_by_comp.items()}
        if sum(map(len, prior_all.values())) < min_prior:
            continue
        fitted = fit_strength(prior_all, as_of=f'{d}T00:00:00Z')
        new_proj = project_goals(fitted, match['hid'], match['aid'], target_comp)
        new = exact_markets(new_proj['home_goals'], new_proj['away_goals'])
        prior_target = prior_all.get(target_comp, [])
        old_ratings, old_base = rating_from_results(
            [{'home': str(m['hid']), 'away': str(m['aid']), 'hg': m['hg'], 'ag': m['ag']}
             for m in prior_target], min_games=1)
        h, a = old_ratings.get(str(match['hid'])), old_ratings.get(str(match['aid']))
        h = h or {'attack': 1, 'defense': 1}
        a = a or {'attack': 1, 'defense': 1}
        xh, xa = expected_goals(h['attack'], h['defense'], a['attack'], a['defense'], old_base, 1.12)
        old = exact_markets(xh, xa)
        actual = 'home_win' if match['hg'] > match['ag'] else 'away_win' if match['hg'] < match['ag'] else 'draw'
        def score(probs):
            return sum((probs[k] - float(k == actual)) ** 2 for k in ('home_win', 'draw', 'away_win'))
        def logloss(probs):
            return -math.log(max(probs[actual], 1e-12))
        output.append({'Date': d, 'Match': f"{match['home']} vs {match['away']}",
                       'Actual': actual, 'V4.4 Brier': score(old), 'V4.5 Brier': score(new),
                       'V4.4 log loss': logloss(old), 'V4.5 log loss': logloss(new),
                       'New home %': round(new['home_win'] * 100, 1),
                       'New draw %': round(new['draw'] * 100, 1),
                       'New away %': round(new['away_win'] * 100, 1)})
    return output
