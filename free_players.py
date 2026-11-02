"""Public football-data.org team squad adapter; roster != lineup."""
import requests

ROOT = "https://api.football-data.org/v4"

class RosterUnavailable(Exception):
    pass


def parse_team_roster(payload):
    """Return available squad records, without guessing starters or scoring rates."""
    records = payload.get('squad') or []
    return [{'Name': p['name'], 'Position': p.get('position') or 'Unknown',
             'Nationality': p.get('nationality') or 'Unknown'}
            for p in records if isinstance(p, dict) and p.get('name')]


def fetch_team_roster(team_id, token):
    if not token:
        raise RosterUnavailable('Missing football-data.org key.')
    try:
        r = requests.get(f'{ROOT}/teams/{int(team_id)}',
                         headers={'X-Auth-Token': token}, timeout=20)
        if r.status_code in (401, 403, 404):
            raise RosterUnavailable('Roster unavailable through the current football-data.org access level.')
        if r.status_code == 429:
            raise RosterUnavailable('Provider rate limit reached; try again later.')
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            raise RosterUnavailable('Unexpected roster response from football-data.org.')
    except (requests.RequestException, ValueError, TypeError) as exc:
        raise RosterUnavailable('Unable to retrieve this roster right now.') from exc
    return parse_team_roster(data)
