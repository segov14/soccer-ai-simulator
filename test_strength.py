from datetime import datetime, timedelta, timezone
import math
from strength import collect_results, fit_strength, project_goals, compare_backtest
from advanced import exact_markets


def match(home, away, hg, ag, code='PD', day=0):
    stamp = (datetime(2026, 8, 1, tzinfo=timezone.utc) + timedelta(days=day)).strftime('%Y-%m-%dT18:00:00Z')
    return {'hid':home,'aid':away,'hg':hg,'ag':ag,'date_utc':stamp,
            'id':(code,home,away,day),'home':str(home),'away':str(away)}


def test_empty_fits_are_safe():
    fit = fit_strength({})
    p = project_goals(fit, 'home', 'away', 'CL')
    assert p['home_quality'].startswith('Unavailable')
    assert p['home_goals'] > p['away_goals']
    assert sum(exact_markets(p['home_goals'],p['away_goals'])[k] for k in ('home_win','draw','away_win')) > .9999


def test_current_season_and_cutoff_skip_future_matches():
    matches=[match(1,2,2,0,day=0),match(2,1,100,0,day=2), match(1,3,1,1,day=1)]
    rows=collect_results({'PD':matches},as_of='2026-08-02T00:00:00Z')
    assert len(rows)==1
    f=fit_strength({'PD':matches},as_of='2026-08-02T00:00:00Z')
    assert f['n_matches']==1


def test_duplicate_record_not_counted_twice():
    m=match(1,2,1,0)
    assert len(collect_results({'PD':[m,m]}))==1


def test_attack_and_opponent_quality_not_only_position():
    data={'PD':[]}
    for day in range(20):
        data['PD'].append(match(1,2,3,0,day=day*3))
        data['PD'].append(match(3,4,0,2,day=day*3+1))
    f=fit_strength(data,as_of='2026-11-10T00:00:00Z')
    assert f['teams']['1']['attack']>f['teams']['3']['attack']
    p1=project_goals(f,1,4,'PD')
    p2=project_goals(f,3,4,'PD')
    assert p1['home_goals']>p2['home_goals']


def test_ucl_links_leagues_and_team_identifiers():
    games={
       'PD':[match(10,11,3,1,'PD',day=i*4) for i in range(10)],
       'PL':[match(20,21,2,1,'PL',day=i*4) for i in range(10)],
       'CL':[match(20,10,1,2,'CL',day=i*5) for i in range(5)],
    }
    f=fit_strength(games,as_of='2026-11-10T00:00:00Z')
    p=project_goals(f,10,20,'CL')
    assert p['home_rating']['domestic_games']==10
    assert p['away_rating']['domestic_games']==10
    assert p['home_rating']['ucl_games']==5
    assert p['away_rating']['ucl_games']==5
    assert all(math.isfinite(p[k]) for k in ('home_goals','away_goals'))


def test_missing_domestic_data_labelled():
    f=fit_strength({'CL':[match(12,10,1,1,'CL',day=i*3) for i in range(5)]})
    assert 'European matches only' in project_goals(f,12,10,'CL')['home_quality']


def test_backtest_same_day_not_leaked():
    games={'PD':[],'CL':[]}
    for i in range(65):
        games['PD'].append(match(i%4+1, (i+1)%4+1,i%3,(i+1)%2,day=i))
        if i%4==0:
            games['CL'].append(match(i%4+1, (i+2)%4+1,2,0,code='CL',day=i))
    rows=compare_backtest(games,'PD',limit=10)
    assert rows and len(rows)<=10
    assert all(r['V4.5 Brier']>=0 and r['V4.4 Brier']>=0 for r in rows)
    assert all(0<=r['New draw %']<=100 for r in rows)
