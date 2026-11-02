"""No secret keys or network access required for these tests."""
import math
import pytest

from odds_data import (SPORT_KEYS, OddsUnavailable, odds_request, find_event,
                       team_similarity, fair_market, american_odds,
                       compare_event, calibration_table)


GAME = {
    'id': 'match-123', 'home_team': 'Real Madrid', 'away_team': 'Liverpool',
    'commence_time': '2026-11-04T20:00:00Z',
    'bookmakers': [{
        'title': 'DemoBook', 'key': 'demo', 'last_update': '2026-11-03T18:00:00Z',
        'markets': [
            {'key': 'h2h', 'last_update': '2026-11-03T18:00:00Z', 'outcomes': [
                {'name': 'Real Madrid', 'price': 2.1},
                {'name': 'Liverpool', 'price': 3.6},
                {'name': 'Draw', 'price': 3.5}
            ]},
            {'key': 'totals', 'last_update': '2026-11-03T18:00:00Z', 'outcomes': [
                {'name': 'Over', 'point': 2.5, 'price': 1.9},
                {'name': 'Under', 'point': 2.5, 'price': 2.0},
            ]},
        ],
    }]
}


def test_league_keys():
    assert SPORT_KEYS['PD'] == 'soccer_spain_la_liga'
    assert SPORT_KEYS['CL'] == 'soccer_uefa_champs_league'
    assert SPORT_KEYS['PL'] == 'soccer_epl'


def test_team_matching_aliases_and_false_friends():
    assert team_similarity('Real Madrid CF', 'Real Madrid') == 1.0
    assert team_similarity('PAE AEK', 'AEK Athens') == 1.0
    assert team_similarity('Manchester City FC', 'Manchester United FC') == 0.0
    assert team_similarity('Real Madrid', 'Atletico Madrid') == 0.0
    assert team_similarity('', 'Liverpool') == 0.0


def test_event_matches_both_teams_and_kickoff():
    result = find_event([GAME], 'Real Madrid CF', 'Liverpool FC', '2026-11-04T19:45:00Z')
    assert result is GAME
    assert find_event([GAME], 'Real Madrid', 'Arsenal', '2026-11-04T20:00:00Z') is None
    assert find_event([GAME], 'Real Madrid', 'Liverpool', '2026-11-07T20:00:00Z') is None
    assert find_event([GAME, dict(GAME, id='dup')], 'Real Madrid', 'Liverpool', '2026-11-04T20:00:00Z') is None


def test_bookmaker_margin_and_ev():
    model = {'home_win': .54, 'draw': .24, 'away_win': .22,
             'over_25': .57, 'under_25': .43}
    rows = compare_event(GAME, model, '2026-11-01T12:00:00Z')
    assert len(rows) == 5
    madrid = next(r for r in rows if r['Outcome'] == 'Home win')
    assert madrid['Model probability'] == .54
    assert math.isclose(madrid['Model EV ROI (%)'], 100 * (.54 * 2.1 - 1))
    assert madrid['Raw implied probability'] == pytest.approx(1 / 2.1)
    assert madrid['No-vig market probability'] < madrid['Raw implied probability']
    assert sum(r['No-vig market probability'] for r in rows if r['Market'] == '90-minute 1X2') == pytest.approx(1)
    assert sum(r['No-vig market probability'] for r in rows if r['Market'] == 'Total goals 2.5') == pytest.approx(1)
    assert len({r['Bookmaker'] for r in rows}) == 1
    assert {r['Event ID'] for r in rows} == {'match-123'}


def test_two_way_soccer_odds_ignored():
    odds = dict(GAME, bookmakers=[{'title': 'Two way', 'markets': [
        {'key': 'h2h', 'outcomes': [{'name': 'Real Madrid', 'price': 1.5}, {'name': 'Liverpool', 'price': 2.0}]}
    ]}])
    assert compare_event(odds, {'home_win': .5, 'draw': .2, 'away_win': .3}, '') == []


def test_other_goal_lines_excluded():
    odds = dict(GAME, bookmakers=[{'title': 'Other totals', 'markets': [
        {'key': 'totals', 'outcomes': [{'name': 'Over', 'point': 3.5, 'price': 1.9},
                                      {'name': 'Under', 'point': 3.5, 'price': 1.9}]}
    ]}])
    assert compare_event(odds, {'over_25': .5, 'under_25': .5}, '') == []


def test_invalid_prices_and_american_odds():
    assert fair_market({'home': 1.0, 'away': 2.0}) is None
    assert fair_market({'home': float('inf'), 'away': 2.0}) is None
    assert fair_market({'home': 2.0, 'away': 2.0})[0]['home'] == pytest.approx(.5)
    assert american_odds(2.1) == 110
    assert american_odds(1.5) == -200
    assert american_odds(1.0) is None


def test_reliability_bins_count_events():
    table = calibration_table([
        {'New home %': 60, 'New draw %': 20, 'New away %': 20, 'Actual': 'home_win'},
        {'New home %': 10, 'New draw %': 30, 'New away %': 60, 'Actual': 'draw'},
    ])
    assert sum(r['Outcomes tested'] for r in table) == 6
    assert all(0 <= row['Observed frequency'] <= 1 for row in table)


class FakeResponse:
    status_code = 200
    headers = {'x-requests-remaining': '480', 'x-requests-used': '20', 'x-requests-last': '1'}
    def json(self):
        return [GAME]


class FakeSession:
    def __init__(self, response=None):
        self.response = response if response is not None else FakeResponse()
        self.params = None
    def get(self, url, params, timeout):
        assert url.endswith('/soccer_epl/odds')
        self.params = params
        assert timeout == 20
        return self.response


def test_api_fetch_with_quota():
    client = FakeSession()
    result = odds_request('soccer_epl', 'private-key', session=client)
    assert len(result['events']) == 1
    assert result['quota']['x-requests-remaining'] == 480
    assert client.params == {'apiKey': 'private-key', 'regions': 'us', 'markets': 'h2h', 'oddsFormat': 'decimal'}
    assert 'private-key' not in str(result)


def test_api_errors_never_expose_key():
    response = FakeResponse()
    response.status_code = 401
    with pytest.raises(OddsUnavailable) as exc:
        odds_request('soccer_epl', 'private-secret', session=FakeSession(response))
    assert 'private-secret' not in str(exc.value)
    assert '401' in str(exc.value)


def test_api_market_choice():
    client = FakeSession()
    odds_request('soccer_epl', 'private-key', region='eu', include_totals=True, session=client)
    assert client.params['markets'] == 'h2h,totals'
    assert client.params['regions'] == 'eu'
