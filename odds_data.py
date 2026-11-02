"""Read bookmaker odds from The Odds API and compare with model probabilities.

All prices are actual provider values, matched conservatively by two teams and
kickoff. Missing markets or ambiguous matches are explicitly unavailable.
No claims of positive expected returns being real-world profitable are made.
"""
from datetime import datetime, timezone
from difflib import SequenceMatcher
import math
import re
import unicodedata

import requests

API_BASE = 'https://api.the-odds-api.com/v4/sports'
SPORT_KEYS = {'PD': 'soccer_spain_la_liga', 'CL': 'soccer_uefa_champs_league', 'PL': 'soccer_epl'}
REGIONS = {'United States': 'us', 'Europe': 'eu', 'United Kingdom': 'uk'}


class OddsUnavailable(Exception):
    """A safe, human-readable, non-secret API or data error."""


def odds_request(sport_key, api_key, region='us', include_totals=False, session=None):
    """Fetch current odds. The API key is sent directly; never return request URL.

    An h2h query costs 1 credit for 1 region, with +1 if totals are requested.
    Both source data and quota counts are returned; the UI controls caching.
    """
    if sport_key not in SPORT_KEYS.values():
        raise ValueError('Unsupported odds competition.')
    if region not in REGIONS.values():
        raise ValueError('Unsupported odds region.')
    if not api_key or not api_key.strip():
        raise OddsUnavailable('ODDS_API_KEY is missing from Streamlit Secrets.')
    requester = session or requests
    try:
        response = requester.get(
            f'{API_BASE}/{sport_key}/odds',
            params={'apiKey': api_key, 'regions': region,
                    'markets': 'h2h,totals' if include_totals else 'h2h',
                    'oddsFormat': 'decimal'},
            timeout=20,
        )
    except requests.RequestException as exc:
        # Avoid exception text: HTTP exception may include URL with secret query.
        raise OddsUnavailable('Could not reach The Odds API. Try again later.') from exc
    status = response.status_code
    if status != 200:
        if status == 401:
            raise OddsUnavailable('The Odds API rejected the key (HTTP 401). Check ODDS_API_KEY in Secrets.')
        if status == 403:
            raise OddsUnavailable('The Odds API denied access (HTTP 403). Check your subscription.')
        if status == 429:
            raise OddsUnavailable('Odds API quota or request limit reached (HTTP 429). Wait or check your dashboard.')
        if status == 422:
            raise OddsUnavailable('The Odds API does not recognize the requested market/competition (HTTP 422).')
        raise OddsUnavailable(f'The Odds API returned HTTP {status}.')
    try:
        events = response.json()
    except ValueError as exc:
        raise OddsUnavailable('The odds provider returned invalid JSON.') from exc
    if not isinstance(events, list):
        raise OddsUnavailable('The odds provider returned an unexpected payload.')
    quota = {}
    for key in ('x-requests-remaining', 'x-requests-used', 'x-requests-last'):
        value = response.headers.get(key)
        try:
            quota[key] = int(value) if value is not None else None
        except (TypeError, ValueError):
            quota[key] = None
    return {'events': events, 'quota': quota,
            'retrieved_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'sport': sport_key, 'region': region}


def _normalized(name):
    s = unicodedata.normalize('NFKD', str(name or '')).encode('ascii', 'ignore').decode('ascii').lower()
    s = re.sub(r'[^a-z0-9 ]+', ' ', s)
    s = ' '.join(w for w in s.split() if w not in {'fc', 'cf', 'ac', 'sc', 'afc', 'cd', 'ud', 'pae', 'club', 'de', 'futbol', 'football', 'rcd', 'sd', 'ca', 'rc'})
    aliases = {
        'aek': 'aek athens', 'aek athina': 'aek athens', 'aek athens': 'aek athens',
        'real madrid': 'real madrid', 'real madrid club': 'real madrid',
        'psg': 'paris saint germain', 'paris sg': 'paris saint germain',
        'inter': 'internazionale milano', 'inter milan': 'internazionale milano',
        'internazionale': 'internazionale milano',
        'atletico de madrid': 'atletico madrid', 'atletico madrid': 'atletico madrid',
        'bayern munchen': 'bayern munich', 'bayern munich': 'bayern munich',
        'borussia dortmund': 'borussia dortmund', 'bvb dortmund': 'borussia dortmund',
        'tottenham hotspur': 'tottenham', 'tottenham': 'tottenham',
        'man utd': 'manchester united', 'man united': 'manchester united',
        'man city': 'manchester city', 'wolves': 'wolverhampton wanderers',
    }
    return aliases.get(s, s)


def team_similarity(first, second):
    a, b = _normalized(first), _normalized(second)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # Reject single shared city/token where opposition could be very different.
    ta, tb = set(a.split()), set(b.split())
    overlap = len(ta & tb)
    if overlap == 0:
        return 0.0
    lexical = SequenceMatcher(None, a, b).ratio()
    if overlap < min(2, len(ta), len(tb)):
        return 0.0
    if lexical < 0.88:
        return 0.0
    return lexical


def parse_datetime(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        return None


def find_event(events, home_name, away_name, kickoff_utc, max_hours=30):
    """Two-team + same-kickoff matching. Fail closed on ambiguity."""
    expected = parse_datetime(kickoff_utc)
    if expected is None:
        return None
    matches = []
    for event in events:
        if not isinstance(event, dict):
            continue
        event_start = parse_datetime(event.get('commence_time'))
        if event_start is None:
            continue
        time_gap = abs((event_start - expected).total_seconds()) / 3600
        if time_gap > max_hours:
            continue
        hs = team_similarity(home_name, event.get('home_team'))
        aas = team_similarity(away_name, event.get('away_team'))
        if min(hs, aas) < 0.88:
            continue
        matches.append((hs + aas - time_gap / 500, event))
    matches.sort(key=lambda item: item[0], reverse=True)
    # Never attach quotes to an uncertain match.
    if len(matches) > 1 and matches[0][0] - matches[1][0] < 0.03:
        return None
    return matches[0][1] if matches else None


def american_odds(price):
    """Convert decimal odds to American format for display only."""
    if not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 1:
        return None
    return round(100 * (price - 1)) if price >= 2 else round(-100 / (price - 1))


def fair_market(odds):
    """Multiplicative no-vig probabilities, valid for complete markets only."""
    if not odds or any(not isinstance(v, (int, float)) or isinstance(v, bool)
                       or not math.isfinite(v) or v <= 1 for v in odds.values()):
        return None
    inv = {k: 1.0 / v for k, v in odds.items()}
    overround = sum(inv.values())
    if overround <= 0:
        return None
    return {k: v / overround for k, v in inv.items()}, overround


def _market_prices(market, event, kind):
    """Reject incomplete soccer markets; never force 2-way h2h into 1X2."""
    outcomes = market.get('outcomes', [])
    if not isinstance(outcomes, list):
        return None
    result = {}
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            continue
        name, price = outcome.get('name'), outcome.get('price')
        if not isinstance(price, (int, float)) or isinstance(price, bool) or not math.isfinite(price) or price <= 1:
            continue
        if kind == 'h2h':
            key = ('home_win' if team_similarity(name, event['home_team']) >= 0.88
                   else 'away_win' if team_similarity(name, event['away_team']) >= 0.88
                   else 'draw' if str(name).strip().lower() in ('draw', 'tie') else None)
            if key:
                result[key] = float(price)
        elif kind == 'totals':
            try:
                is_target = abs(float(outcome.get('point')) - 2.5) < 0.001
            except (ValueError, TypeError):
                is_target = False
            if is_target and str(name).lower() in ('over', 'under'):
                result['over_25' if str(name).lower() == 'over' else 'under_25'] = float(price)
    wanted = {'home_win', 'draw', 'away_win'} if kind == 'h2h' else {'over_25', 'under_25'}
    return result if set(result) == wanted else None


def compare_event(event, model_probs, retrieved_utc):
    """Each bookmaker is independently de-vigged; avoid cherry-picked combos."""
    rows = []
    for bookmaker in event.get('bookmakers', []):
        if not isinstance(bookmaker, dict):
            continue
        for market in bookmaker.get('markets', []):
            if not isinstance(market, dict):
                continue
            kind = market.get('key')
            if kind not in ('h2h', 'totals'):
                continue
            odds = _market_prices(market, event, kind)
            if not odds:
                continue
            market_fair = fair_market(odds)
            if market_fair is None:
                continue
            fair, margin = market_fair
            for outcome, price in odds.items():
                p = model_probs.get(outcome)
                if p is None or not 0 <= p <= 1 or not math.isfinite(p):
                    continue
                risk_pct = 100 * (p * price - 1)
                us_odds = american_odds(price)
                rows.append({
                    'Market': '90-minute 1X2' if kind == 'h2h' else 'Total goals 2.5',
                    'Outcome': {'home_win': 'Home win', 'draw': 'Draw', 'away_win': 'Away win',
                                'over_25': 'Over 2.5', 'under_25': 'Under 2.5'}[outcome],
                    'Bookmaker': bookmaker.get('title') or bookmaker.get('key') or 'Unknown',
                    'Decimal odds': price,
                    'American odds': f'+{us_odds}' if us_odds is not None and us_odds > 0 else str(us_odds),
                    'Model probability': p,
                    'Raw implied probability': 1 / price,
                    'No-vig market probability': fair[outcome],
                    'Model-market edge (pp)': 100 * (p - fair[outcome]),
                    'Model EV ROI (%)': risk_pct,
                    'Model EV per $100': risk_pct,
                    'Bookmaker margin (%)': 100 * (margin - 1),
                    'Odds last updated (UTC)': market.get('last_update') or bookmaker.get('last_update'),
                    'Snapshot retrieved (UTC)': retrieved_utc,
                    'Event kickoff (UTC)': event.get('commence_time'),
                    'Event ID': event.get('id'),
                    'Uncalibrated model': True,
                })
    return sorted(rows, key=lambda r: r['Model EV ROI (%)'], reverse=True)


def calibration_table(backtest_rows):
    """Honest small-sample reliability *diagnostic*, not fitted calibration."""
    outcomes = [('home_win', 'New home %'), ('draw', 'New draw %'), ('away_win', 'New away %')]
    points = []
    for row in backtest_rows:
        for target, field in outcomes:
            try:
                p = float(row[field]) / 100
            except (TypeError, ValueError, KeyError):
                continue
            if 0 <= p <= 1:
                points.append((p, int(row.get('Actual') == target)))
    out = []
    for i in range(5):
        subset = [(p, y) for p, y in points if (i / 5 <= p < (i + 1) / 5 or (i == 4 and p == 1))]
        if not subset:
            continue
        out.append({'Probability bin': f'{i*20}–{(i+1)*20}%',
                    'Outcomes tested': len(subset),
                    'Mean predicted': sum(p for p, _ in subset) / len(subset),
                    'Observed frequency': sum(y for _, y in subset) / len(subset)})
    return out
