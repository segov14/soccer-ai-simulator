from advanced import exact_markets, corner_markets, anytime_scorer, rolling_backtest

def test_exact():
    p = exact_markets(2.3, 1.88)
    assert abs(sum(p[k] for k in ('home_win','draw','away_win')) - 1) < 1e-9
    assert 0.15 < p['draw'] < .25

def test_corners():
    c = corner_markets(5.2, 4.2)
    assert c['over_75'] > c['over_85'] > c['over_95'] > c['over_105']

def test_scorer():
    assert anytime_scorer(2, .3, 90, 1) > anytime_scorer(2, .3, 60, .8)

def test_backtest():
    sample=[]
    for i in range(80):
        sample.append({'id': i, 'date_utc': f'2026-01-{(i//4)+1:02d}T12:00:00Z',
                       'home':'A' if i%2 else 'B','away':'B' if i%2 else 'A',
                       'hid':1 if i%2 else 2,'aid':2 if i%2 else 1,'hg':i%3,'ag':(i+1)%3})
    rows = rolling_backtest(sample)
    assert len(rows)>0 and all(r['brier']>=0 for r in rows)
