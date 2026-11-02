from automatic_scorers import scorer_scenarios, role_for_position

def test_role_mapping():
    assert role_for_position('Centre-Forward') == 'Attack'
    assert role_for_position('Defender') == 'Defence'
    assert role_for_position('Central Midfield') == 'Midfield'
    assert role_for_position('Unknown') == 'Unknown'

def test_conditional_scenario():
    roster = [{'Name': 'A', 'Position': 'Centre-Forward'}, {'Name': 'B', 'Position': 'Goalkeeper'}, {'Name': 'C', 'Position': None}]
    rows = scorer_scenarios(roster, 2.0)
    assert len(rows) == 3
    assert rows[0]['Player'] == 'A'
    assert 0 < rows[0]['Chance if playing'] < 1
    assert rows[2]['Chance if playing'] is None

def test_more_goals_means_more_chance():
    roster = [{'Name': 'A', 'Position': 'Attacker'}]
    assert scorer_scenarios(roster, 2.0)[0]['Chance if playing'] > scorer_scenarios(roster, 1.0)[0]['Chance if playing']


def test_common_attacking_role_labels():
    for label in ('Offence', 'Offense', 'Left Wing', 'Right Wing', 'LW', 'RW', 'Centre Forward', 'Center-Forward', 'Striker', 'Attacker', 'Left Winger', 'CF'):
        assert role_for_position(label) == 'Attack', label

def test_all_players_remain_even_if_role_missing():
    roster = [{'Name':'Mbappé', 'Position':'Offence'}, {'Name':'Vinícius', 'Position':'Left Wing'}, {'Name':'Diomande', 'Position':'Right Winger'}, {'Name':'Unknown player', 'Position':None}]
    rows = scorer_scenarios(roster, 1.8)
    by_name = {r['Player']: r for r in rows}
    assert len(rows) == len(roster)
    assert all(by_name[n]['Chance if playing'] is not None for n in ('Mbappé', 'Vinícius', 'Diomande'))
    assert by_name['Unknown player']['Chance if playing'] is None
