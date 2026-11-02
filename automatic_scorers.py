"""Transparent role-only goal scenarios; NOT empirical player forecasts."""
import math

# Each hypothetical XI has 3 forwards, 4 midfielders, 3 defenders and a GK.
# These are illustrative role weights, not measured player scoring rates.
ROLE_WEIGHT = {'Attack': 1.0, 'Midfield': 0.48, 'Defence': 0.16, 'Goalkeeper': 0.01}
DENOMINATOR = 3 * 1.0 + 4 * 0.48 + 3 * 0.16 + 0.01


def role_for_position(position):
    """Normalize common football-data.org and third-party position spellings.

    Unknown stays unknown: a squad listing alone cannot establish a player's role.
    """
    import re
    raw = str(position or '').strip().casefold()
    p = re.sub(r'[^a-z0-9]+', ' ', raw).strip()
    compact = p.replace(' ', '')
    if not p or p in ('none', 'null', 'unknown', 'n a', 'not available', 'unspecified'):
        return 'Unknown'
    if any(x in compact for x in ('goalkeeper', 'goalie', 'keeper', 'goaltender')) or compact in ('gk',):
        return 'Goalkeeper'
    if any(x in compact for x in ('defence', 'defense', 'defender', 'centreback', 'centerback', 'fullback', 'wingback')) or compact in ('cb', 'lb', 'rb', 'lwb', 'rwb'):
        return 'Defence'
    if any(x in compact for x in ('midfield', 'midfielder', 'playmaker')) or compact in ('cm', 'cdm', 'cam', 'dm', 'am', 'lm', 'rm'):
        return 'Midfield'
    if any(x in compact for x in ('attack', 'offence', 'offense', 'forward', 'striker', 'winger', 'secondstriker')) or compact in ('cf', 'st', 'ss', 'lw', 'rw', 'lf', 'rf') or p in ('left wing', 'right wing', 'centre forward', 'center forward'):
        return 'Attack'
    return 'Unknown'


def scorer_scenarios(roster, team_expected_goals, assumed_minutes=75):
    """Return conditional chances IF player plays, using role-only hypothetical XI.

    Does not infer likely starters, player goals/minutes or betting odds.
    Unknown positions have no estimate.
    """
    if not 0 <= float(team_expected_goals) <= 10:
        raise ValueError('Invalid team goal assumption')
    if not 0 <= int(assumed_minutes) <= 90:
        raise ValueError('Invalid minute assumption')
    out = []
    for entry in roster:
        role = role_for_position(entry.get('Position'))
        weight = ROLE_WEIGHT.get(role)
        chance = (1.0 - math.exp(-float(team_expected_goals) * weight /
                 DENOMINATOR * int(assumed_minutes) / 90)) if weight is not None else None
        out.append({'Player': entry.get('Name', ''), 'Listed position': entry.get('Position', 'Unknown'),
                    'Role category': role, 'Chance if playing': chance})
    return sorted(out, key=lambda x: (x['Chance if playing'] is None, -(x['Chance if playing'] or 0), x['Player']))
