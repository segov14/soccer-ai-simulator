"""Independent probabilistic add-ons; no claims of calibrated betting accuracy."""
import math
import numpy as np
from model import expected_goals, rating_from_results


def poisson_distribution(mean, cutoff=34):
    """Poisson probabilities with residual mass collected into last bin."""
    mean = max(0.0, float(mean))
    p = math.exp(-mean)
    values = [p]
    for k in range(1, cutoff):
        p *= mean / k
        values.append(p)
    values.append(max(0.0, 1 - sum(values)))
    return np.asarray(values)


def exact_markets(home_mean, away_mean):
    """Exact Poisson match odds (not Monte Carlo sampling)."""
    h = poisson_distribution(home_mean, 30)
    a = poisson_distribution(away_mean, 30)
    matrix = np.outer(h, a)
    hi, ai = np.indices(matrix.shape)
    return {"home_win": float(matrix[hi > ai].sum()),
            "draw": float(matrix[hi == ai].sum()),
            "away_win": float(matrix[hi < ai].sum()),
            "over_25": float(matrix[hi + ai > 2].sum()),
            "under_25": float(matrix[hi + ai <= 2].sum()),
            "btts": float(matrix[(hi > 0) & (ai > 0)].sum())}


def corner_markets(home_corners, away_corners):
    """Illustrative Poisson corner model assuming independent team counts."""
    home_corners = float(home_corners)
    away_corners = float(away_corners)
    if not 0 <= home_corners <= 20 or not 0 <= away_corners <= 20:
        raise ValueError('Corner assumptions must be between 0 and 20.')
    total = home_corners + away_corners
    d = poisson_distribution(total, 50)
    return {"expected_total": total, "home": home_corners, "away": away_corners,
            "over_75": float(d[8:].sum()), "over_85": float(d[9:].sum()),
            "over_95": float(d[10:].sum()), "over_105": float(d[11:].sum())}


def anytime_scorer(team_goals, scoring_share, minutes=90, starting_probability=1.0):
    """Probability player scores >=1 based on ASSUMED team goal share and minutes."""
    if not (0 <= scoring_share <= 1 and 0 <= minutes <= 120 and 0 <= starting_probability <= 1):
        raise ValueError('Invalid player assumptions.')
    conditional = 1 - math.exp(-max(0, float(team_goals)) * scoring_share * minutes / 90)
    return float(starting_probability * conditional)


def rolling_backtest(finished, min_prior=20):
    """Strict chronological, no future match outcomes included in a prediction.

    Backtest within one returned competition/season; results are illustrative and
    do not imply independence or real-world calibration.
    """
    ordered = sorted(finished, key=lambda m: (m.get('date_utc') or '', m.get('id') or 0))
    rows = []
    for i, match in enumerate(ordered):
        # Exclude ALL games on the same calendar day to prevent same-day leakage.
        cutoff = (match.get('date_utc') or '')[:10]
        prior = [m for m in ordered[:i] if (m.get('date_utc') or '')[:10] < cutoff]
        if len(prior) < min_prior:
            continue
        training = [{'home': str(m['hid']), 'away': str(m['aid']), 'hg': m['hg'], 'ag': m['ag']} for m in prior]
        ratings, base = rating_from_results(training, min_games=1)
        h = ratings.get(str(match['hid']))
        a = ratings.get(str(match['aid']))
        if h is None or a is None or min(h['games'], a['games']) < 3:
            continue
        hg, ag = expected_goals(h['attack'], h['defense'], a['attack'], a['defense'], base, 1.12)
        odds = exact_markets(hg, ag)
        outcome = 'home_win' if match['hg'] > match['ag'] else 'away_win' if match['hg'] < match['ag'] else 'draw'
        rows.append({'date': cutoff, 'home': match['home'], 'away': match['away'],
                     'home_goals': match['hg'], 'away_goals': match['ag'],
                     'prob_home': odds['home_win'], 'prob_draw': odds['draw'], 'prob_away': odds['away_win'],
                     'actual': outcome, 'prob_actual': odds[outcome],
                     'brier': sum((odds[k] - int(k == outcome)) ** 2 for k in ('home_win', 'draw', 'away_win')),
                     'log_loss': -math.log(max(odds[outcome], 1e-12))})
    return rows
