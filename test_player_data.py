from player_data import match_fixture, stats_rows, lineup_players, estimate_scorers


def test_fixture_mapping_by_date_and_names():
    fixtures = [{'fixture': {'id': 66, 'date': '2026-11-04T20:00:00+00:00'}, 'teams': {'home': {'id': 1, 'name': 'AEK Athens FC'}, 'away': {'id': 2, 'name': 'Real Madrid CF'}}}]
    found = match_fixture(fixtures, 'PAE AEK', 'Real Madrid CF', '2026-11-04T20:00:00Z')
    assert found['fixture']['id'] == 66
    assert match_fixture(fixtures, 'Manchester City', 'Real Madrid', '2026-11-04T20:00:00Z') is None


def test_missing_lineups_or_stats_not_invented():
    assert lineup_players([], 2) == []
    assert estimate_scorers([], [{'id': 5, 'name': 'A'}], 2) == []
    assert stats_rows([{'player': {'name': 'A'}, 'statistics': [{'goals': {'total': None}, 'games': {'minutes': 0}}]}]) == []


def test_scorer_estimate_stays_in_probability_range():
    rows = [{'id': 5, 'name': 'A', 'goals': 5, 'minutes': 900, 'goals_per90': .5},
            {'id': 6, 'name': 'B', 'goals': 2, 'minutes': 900, 'goals_per90': .2}]
    out = estimate_scorers(rows, [{'id': 5, 'name': 'A'}, {'id': 6, 'name': 'B'}], 2.0)
    assert len(out) == 2 and all(0 <= r['Anytime chance (illustrative)'] <= 1 for r in out)
