import math
from datetime import date
from unittest.mock import Mock
import pytest

from season_stats import (current_season_year, valid_season, parse_scorers, fetch_scorers,
                          StatsUnavailable, team_totals_by_comp, combine_player_rows,
                          season_matches_only)


def example_payload(year=2026):
    return {"season": {"startDate": f"{year}-08-20", "endDate": f"{year+1}-05-29"},
            "filters": {"season": str(year), "limit": 200},
            "scorers": [
                {"player": {"id": 9, "name": "Kylian Mbappé"}, "team": {"id": 86, "name": "Real Madrid"},
                 "goals": 11, "assists": 3, "penalties": 2},
                {"player": {"id": 7, "name": "Vinícius Júnior"}, "team": {"id": 86, "name": "Real Madrid"},
                 "goals": 4, "assists": 5, "penalties": None},
            ]}


def test_year_current_uses_july_start():
    assert current_season_year(date(2026, 11, 1)) == 2026
    assert current_season_year(date(2027, 2, 1)) == 2026
    assert current_season_year(date(2027, 8, 1)) == 2027


def test_provider_season_mismatch_rejected():
    assert valid_season(example_payload(), 2026)
    with pytest.raises(StatsUnavailable):
        parse_scorers(example_payload(2025), 'PD', 2026)
    with pytest.raises(StatsUnavailable):
        parse_scorers({"scorers": []}, 'PD', 2026)


def test_player_goal_totals_not_position_based():
    feed, trunc = parse_scorers(example_payload(), 'PD', 2026)
    assert not trunc and len(feed) == 2
    assert feed[0]["goals"] == 11 and feed[0]["assists"] == 3
    roster = [{"ID": 9, "Name": "Kylian Mbappé", "Position": "Offence"},
              {"ID": 7, "Name": "Vinícius Júnior", "Position": "Offence"},
              {"ID": 99, "Name": "Different Forward", "Position": "Offence"},
              {"ID": 77, "Name": "Diomande", "Position": "Midfield"}]
    totals = {(86, "PD"): {"games": 10, "goals": 30}}
    rows = combine_player_rows(roster, 86, {"PD": feed}, totals, 2.1)
    by_name = {r['Player']: r for r in rows}
    assert by_name['Kylian Mbappé']['Anytime chance (experimental)'] > by_name['Vinícius Júnior']['Anytime chance (experimental)']
    assert by_name['Different Forward']['Anytime chance (experimental)'] is None
    assert by_name['Different Forward']['Goals'] is None
    assert by_name['Diomande']['Goals'] is None
    assert by_name['Kylian Mbappé']['Goals'] == 11
    assert by_name['Vinícius Júnior']['Assists'] == 5
    assert math.isclose(by_name['Kylian Mbappé']['Anytime chance (experimental)'], 1-math.exp(-2.1 * 11/30))


def test_combine_competitions_but_only_matching_team_and_id():
    pd, _ = parse_scorers(example_payload(), 'PD', 2026)
    cl = [dict(pd[0], code='CL', goals=3, assists=1, penalties=0)]
    totals = {(86, 'PD'): {'games':10, 'goals':30}, (86, 'CL'): {'games':5, 'goals':12}}
    roster = [{'ID':9, 'Name':'Kylian Mbappé', 'Position':'Offence'}]
    rows = combine_player_rows(roster, 86, {'PD':pd, 'CL':cl}, totals, 2.0)
    assert rows[0]['Goals'] == 14
    assert rows[0]['Assists'] == 4
    assert rows[0]['Team matches'] == 15
    assert rows[0]['Team goals'] == 42


def test_unmatched_id_not_name_guess():
    feed, _ = parse_scorers(example_payload(), 'PD', 2026)
    row = combine_player_rows([{'ID': 10, 'Name': 'Kylian Mbappé'}], 86,
                              {'PD':feed}, {(86,'PD'):{'games': 4, 'goals': 12}}, 2.0)[0]
    assert row['Goals'] is None


def test_missing_results_no_anytime_estimate():
    feed, _ = parse_scorers(example_payload(), 'PD', 2026)
    rows = combine_player_rows([{'ID': 9, 'Name': 'Kylian Mbappé'}], 86, {'PD': feed}, {}, 2.0)
    assert rows[0]['Goals'] == 11
    assert rows[0]['Anytime chance (experimental)'] is None


def test_only_2026_season_dates_retained():
    games = [{'date_utc':'2026-04-01T12:00:00Z'}, {'date_utc':'2026-11-04T12:00:00Z'},
             {'date_utc':'2027-03-01T12:00:00Z'}, {'date_utc':'2027-08-01T12:00:00Z'}]
    final, next_ = season_matches_only(games[:2], games[2:], 2026)
    assert len(final) == 1 and len(next_) == 1


def test_http_season_query_and_auth():
    res = Mock(status_code=200)
    res.json.return_value = example_payload()
    get = Mock(return_value=res)
    rows, truncated = fetch_scorers('PD', 'SECRET', 2026, requester=get)
    assert rows[0]['name'] == 'Kylian Mbappé'
    assert get.call_args.kwargs['params']['season'] == 2026
    assert get.call_args.kwargs['headers']['X-Auth-Token'] == 'SECRET'


def test_http_forbidden_graceful():
    res = Mock(status_code=403)
    with pytest.raises(StatsUnavailable, match='not included'):
        fetch_scorers('PL', 'SECRET', 2026, requester=Mock(return_value=res))


def test_top_scorer_limit_flagged():
    payload = example_payload()
    payload['filters']['limit'] = 2
    _, maybe_trunc = parse_scorers(payload, 'PD', 2026)
    assert maybe_trunc


def test_team_totals_only_results():
    totals = team_totals_by_comp({'PD':[{'hid':86, 'aid':1, 'hg':2, 'ag':1},
                                         {'hid':2, 'aid':86, 'hg':0, 'ag':3}]})
    assert totals[(86,'PD')]['goals'] == 5
    assert totals[(86,'PD')]['games'] == 2
