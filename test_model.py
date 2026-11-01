from model import expected_goals, simulate, rating_from_results

def test_probabilities():
    h, a = expected_goals(1.2, .9, 1.1, 1.0)
    r = simulate(h, a, 10000, seed=42)
    assert abs(r['home_win'] + r['draw'] + r['away_win'] - 1) < 1e-10
    assert abs(r['over_25'] + r['under_25'] - 1) < 1e-10
    assert r == simulate(h, a, 10000, seed=42)

def test_ratings():
    d, avg = rating_from_results([{'home':'A','away':'B','hg':2,'ag':1} for _ in range(4)])
    assert d['A']['attack'] > d['B']['attack']
    assert d['A']['defense'] < d['B']['defense']

if __name__ == '__main__':
    test_probabilities()
    test_ratings()
    print('PASS')
