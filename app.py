import os
import requests
import pandas as pd
import streamlit as st
from model import expected_goals, simulate, rating_from_results

st.set_page_config(page_title='Soccer Simulation Lab', page_icon='⚽', layout='wide')
st.title('⚽ Soccer Simulation Lab')
st.caption('La Liga · UEFA Champions League · Premier League | Experimental probability model, not verified betting advice')

COMPETITIONS = {'La Liga': 'PD', 'Champions League': 'CL', 'Premier League': 'PL'}

@st.cache_data(ttl=1800, show_spinner=False)
def api_matches(code: str, token: str):
    r = requests.get(f'https://api.football-data.org/v4/competitions/{code}/matches',
                     headers={'X-Auth-Token': token}, timeout=20)
    r.raise_for_status()
    matches = []
    upcoming = []
    for m in r.json().get('matches', []):
        home = m.get('homeTeam', {}).get('name')
        away = m.get('awayTeam', {}).get('name')
        if not home or not away:
            continue
        score = m.get('score', {}).get('fullTime', {}) or {}
        if m.get('status') == 'FINISHED' and isinstance(score.get('home'), int) and isinstance(score.get('away'), int):
            matches.append({'home': home, 'away': away, 'hg': score['home'], 'ag': score['away']})
        elif m.get('status') in {'SCHEDULED', 'TIMED'}:
            upcoming.append({'date_utc': m.get('utcDate', ''), 'home': home, 'away': away})
    return matches, sorted(upcoming, key=lambda x: x['date_utc'])

with st.sidebar:
    st.header('Match setup')
    competition = st.selectbox('Competition', list(COMPETITIONS))
    source = st.radio('Ratings source', ['Manual estimates', 'Football-data.org API'], help='API mode fetches current competition results. Manual mode makes no claim to use real stats.')
    n = st.select_slider('Simulations', [1000, 5000, 10000, 25000, 50000, 100000], value=10000)
    seed = st.number_input('Random seed', min_value=0, max_value=1000000, value=42)
    neutral = st.checkbox('Neutral venue', value=False)

ratings = {}
fixtures = []
base_goals = 1.35
if source == 'Football-data.org API':
    token = st.text_input('Football-data.org API key', type='password', value=os.getenv('FOOTBALL_DATA_API_KEY', ''), help='Kept in this session. You can also set the FOOTBALL_DATA_API_KEY environment variable.')
    if token:
        try:
            matches, fixtures = api_matches(COMPETITIONS[competition], token)
            ratings, base_goals = rating_from_results(matches)
            st.info(f'Loaded {len(matches)} finished matches and {len(fixtures)} upcoming fixtures. {len(ratings)} teams have at least 3 results. Ratings are rough goals-based estimates, not xG or lineup-aware.')
        except requests.RequestException as exc:
            st.error(f'Could not load matches: {exc}. Verify your API key and competition permissions.')
    else:
        st.warning('Enter your API key to load current matches. You can use Manual estimates instead.')

if fixtures:
    options = [f"{x['date_utc'][:16].replace('T',' ')} UTC · {x['home']} vs {x['away']}" for x in fixtures]
    picked = st.selectbox('Upcoming fixture', options)
    fixture = fixtures[options.index(picked)]
    home_name, away_name = fixture['home'], fixture['away']
else:
    col1, col2 = st.columns(2)
    with col1:
        home_name = st.text_input('Home team', value='Real Madrid')
    with col2:
        away_name = st.text_input('Away team', value='Barcelona')

home_rating = ratings.get(home_name, {'attack': 1.20, 'defense': 0.88, 'games': 0})
away_rating = ratings.get(away_name, {'attack': 1.10, 'defense': 0.95, 'games': 0})
if source == 'Football-data.org API' and ratings:
    missing = [x for x in (home_name, away_name) if x not in ratings]
    if missing:
        st.warning('Insufficient match history for: ' + ', '.join(missing) + '. Using illustrative default ratings for those teams.')

st.subheader(f'{home_name or "Home"} vs {away_name or "Away"}')
st.caption('Attack >1 means stronger scoring; defense <1 means fewer goals conceded. Change assumptions to explore scenarios.')
c1, c2, c3, c4 = st.columns(4)
with c1:
    ha = st.number_input('Home attack', min_value=0.4, max_value=2.0, value=round(home_rating['attack'], 2), step=0.05)
with c2:
    hd = st.number_input('Home defense', min_value=0.4, max_value=2.0, value=round(home_rating['defense'], 2), step=0.05)
with c3:
    aa = st.number_input('Away attack', min_value=0.4, max_value=2.0, value=round(away_rating['attack'], 2), step=0.05)
with c4:
    ad = st.number_input('Away defense', min_value=0.4, max_value=2.0, value=round(away_rating['defense'], 2), step=0.05)
col1, col2 = st.columns(2)
with col1:
    goal_base = st.slider('Average goals per team (baseline)', 0.7, 2.2, float(round(base_goals, 2)), 0.05)
with col2:
    advantage = st.slider('Home advantage multiplier', 1.0, 1.4, 1.12, 0.01, disabled=neutral)

hxg, axg = expected_goals(ha, hd, aa, ad, goal_base, advantage, neutral)
result = simulate(hxg, axg, n=n, seed=seed)
a, b, c = st.columns(3)
a.metric(f'{home_name or "Home"} win', f"{result['home_win']:.1%}")
b.metric('Draw', f"{result['draw']:.1%}")
c.metric(f'{away_name or "Away"} win', f"{result['away_win']:.1%}")
st.write(f'**Expected goals:** {home_name}: {hxg:.2f} · {away_name}: {axg:.2f} | **Simulations:** {n:,}')
ch1, ch2 = st.columns(2)
with ch1:
    st.subheader('Result probabilities')
    st.bar_chart(pd.DataFrame({'Probability': [result['home_win'], result['draw'], result['away_win']]}, index=[f'{home_name} wins', 'Draw', f'{away_name} wins']))
with ch2:
    st.subheader('Goals markets')
    st.bar_chart(pd.DataFrame({'Probability': [result['over_25'], result['under_25'], result['btts']]}, index=['Over 2.5', 'Under 2.5', 'Both score']))
st.subheader('Most common exact scores')
scores_df = pd.DataFrame(result['scores'], columns=['Final score (home-away)', 'Probability'])
st.dataframe(scores_df.style.format({'Probability': '{:.1%}'}), use_container_width=True, hide_index=True)
report = pd.DataFrame([{'competition': competition, 'home': home_name, 'away': away_name, 'home_xg': hxg,
                        'away_xg': axg, 'home_win': result['home_win'], 'draw': result['draw'],
                        'away_win': result['away_win'], 'over_2_5': result['over_25'],
                        'btts': result['btts'], 'simulations': n, 'seed': seed,
                        'ratings_source': source}])
st.download_button('Download simulation CSV', report.to_csv(index=False).encode('utf-8'), 'simulation.csv', 'text/csv')
st.caption('LIMITATIONS: Independent Poisson goals and simple team ratings. No live injuries, lineups, player props, correlated scores, or bookmaker odds. Current-season small samples can mislead; calibrate and backtest before relying on any betting estimate.')
