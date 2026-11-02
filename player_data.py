"""API-Football adapter. Never invent missing player data or starting elevens."""
import difflib
import math
import re
import requests

ROOT = 'https://v3.football.api-sports.io'
LEAGUES = {'PD': 140, 'PL': 39, 'CL': 2}


def normalize(name):
    value = re.sub(r'[^a-z0-9 ]+', ' ', (name or '').lower())
    words = {'fc', 'cf', 'afc', 'sc', 'ud', 'club', 'de', 'pae', 'the', 'football'}
    return ' '.join(w for w in value.split() if w not in words)


def similarity(a, b):
    a, b = normalize(a), normalize(b)
    if a == b and a: return 1.0
    if a and b and (a in b or b in a): return 0.90
    return difflib.SequenceMatcher(None, a, b).ratio()


def request(path, params, key):
    if not key:
        raise ValueError('API_FOOTBALL_KEY missing from Streamlit Secrets.')
    try:
        r = requests.get(ROOT + '/' + path, params=params,
                         headers={'x-apisports-key': key}, timeout=20)
        r.raise_for_status()
        obj = r.json()
    except requests.RequestException as ex:
        raise ValueError(f'API-Football request failed: {ex}') from ex
    if obj.get('errors'):
        # Never echo an API token; provider errors are usually safe but suppress raw details.
        raise ValueError('API-Football rejected the request or this endpoint/season is not included in your plan.')
    return obj.get('response') or []


def match_fixture(fixtures, home, away, utc_date):
    date = (utc_date or '')[:10]
    candidates = []
    for f in fixtures:
        teams = f.get('teams') or {}
        h = teams.get('home') or {}; a = teams.get('away') or {}
        hd = similarity(home, h.get('name')); ad = similarity(away, a.get('name'))
        fd = (f.get('fixture') or {}).get('date', '')[:10]
        if fd != date or min(hd, ad) < 0.68:
            continue
        candidates.append((hd + ad, f))
    if not candidates:
        return None
    candidates.sort(reverse=True, key=lambda x: x[0])
    return candidates[0][1] if len(candidates) == 1 or candidates[0][0] - candidates[1][0] > .12 else None


def fixture_lookup(code, home, away, utc_date, key):
    league = LEAGUES[code]
    date = (utc_date or '')[:10]
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        return None
    # Competition season starts in summer; calendar dates in Jan-Jun belong to prior season.
    year, month = int(date[:4]), int(date[5:7])
    season = year if month >= 7 else year - 1
    results = request('fixtures', {'league': league, 'season': season, 'date': date}, key)
    return match_fixture(results, home, away, utc_date)


def squad(team_id, key):
    results = request('players/squads', {'team': team_id}, key)
    return (results[0].get('players') or []) if results else []


def lineups(fixture_id, key):
    return request('fixtures/lineups', {'fixture': fixture_id}, key)


def player_statistics(team_id, season, key):
    # First page only for quota protection. Never claim complete statistics.
    return request('players', {'team': team_id, 'season': season, 'page': 1}, key)


def stats_rows(response):
    rows = []
    for entry in response:
        p = entry.get('player') or {}
        stats = (entry.get('statistics') or [{}])[0]
        apps = stats.get('games') or {}; goals = stats.get('goals') or {}
        mins = apps.get('minutes') or 0; appearances = apps.get('appearences') or 0
        n_goals = goals.get('total')
        if not p.get('name') or not isinstance(n_goals, int) or mins <= 0:
            continue
        rows.append({'id': p.get('id'), 'name': p['name'], 'position': apps.get('position'),
                     'minutes': int(mins), 'appearances': appearances, 'goals': n_goals,
                     'goals_per90': 90 * n_goals / mins})
    return sorted(rows, key=lambda x: x['goals_per90'], reverse=True)


def lineup_players(items, team_id):
    for side in items:
        if (side.get('team') or {}).get('id') == team_id:
            return [{'id': (it.get('player') or {}).get('id'), 'name': (it.get('player') or {}).get('name'),
                     'position': (it.get('player') or {}).get('pos')}
                    for it in side.get('startXI') or []]
    return []


def estimate_scorers(rows, starters, team_goals, expected_minutes=80):
    """Illustrative proportional goal-rate allocation; NOT calibrated player probabilities."""
    if not starters:
        return []
    by_id = {p['id']: p for p in rows}
    matches = [(p, by_id[p['id']]) for p in starters if p.get('id') in by_id]
    # Missing player statistics => omit player rather than invent a goal rate.
    total_rate = sum(max(0, s['goals_per90']) for _, s in matches)
    if total_rate <= 0:
        return []
    output = []
    for p, s in matches:
        share = max(0, s['goals_per90']) / total_rate
        expected_player_goals = float(team_goals) * share * expected_minutes / 90
        output.append({'Player': p['name'], 'Goals': s['goals'], 'Minutes (season)': s['minutes'],
                       'Anytime chance (illustrative)': 1 - math.exp(-expected_player_goals)})
    return sorted(output, key=lambda item: item['Anytime chance (illustrative)'], reverse=True)
