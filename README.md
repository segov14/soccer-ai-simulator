# ⚽ Soccer AI Simulator V4.4 — 2026/27 verified-season scorer data

Streamlit app for La Liga, Champions League and Premier League. Version 4.4 replaces equal-by-position automatic player percentages with **individual, current-season, provider-reported** goals and scorer estimates.

## What's new

- Loads football-data.org **2026/27 season** scorer feeds for `PD`, `PL`, and `CL` using `GET /v4/competitions/{code}/scorers?season=2026&limit=200` (tries smaller limits if unsupported).
- Matches scorers to each current roster by **player ID** (falls back to unique full name only if roster has no ID).
- Displays **this-season reported goals, assists, penalties, combined goal involvements, team games, team goals, scoring share and the competitions for which stats were available**. Assists and penalties appear unavailable when data is incomplete.
- Calculates *experimental* anytime-scorer estimates separately for players with available scorer records and sufficient team results. Two forwards with different individual goal records can now have different percentages.
- Includes a published-scorers season overview for all three competitions and downloadable CSVs.
- Current-season API requests and kickoff-date filtering guard against accidentally mixing older seasons.
- Preserves match predictions, corners' manually supplied assumptions, and historical backtesting.
- Caches scorer results for 1 hour, matches for 30 minutes, rosters for 24 hours; refresh happens when users use the app.
- Gracefully explains missing scorer data from the free API rather than inventing player records.

## How player chances are estimated

For players with official provider scorer entries and team goals for **the same** competition(s):

- `share = player's published 2026/27 goals / club's completed-match goals in those published competitions`
- `lambda_player = projected_team_goals_in_selected_match × share`
- `P(player scores ≥ 1) = 1 − exp(−lambda_player)`

This is **an extrapolation**, not a validated player-level betting prediction. It does **not** control for starts, playing time, injuries, transfer effects, goals penalties, opponents faced, xG, shots, or whether the published top-scorer list was truncated. It assumes the published goal share will continue. Probabilities for players *not* in the published scorer feed display **No verified player scoring data**, not zero. If the club's current-season results can't be retrieved, no percentage is computed. Season changes automatically in July.

**Critical data limitation:** football-data.org's scorer feed supplies published goals, assists and penalty totals for listed top scorers — not a full squad-by-squad player statistics API. We cannot automatically provide all players' shots on target, minutes, xG, or confirmed lineups from the user's current free API subscriptions. Missing fields are unavailable, never invented. Access to the scorer feed may depend on the football-data.org plan. API-Football free plan's current-season access is not used.

## Deployment (existing GitHub + Streamlit app)

1. Extract `soccer_ai_simulator_v4_4.zip` on your PC.
2. Go to your GitHub repository `segov14/soccer-ai-simulator` → **Add file** → **Upload files**.
3. Upload the **individual files inside** the extracted ZIP to the repo root; replace existing files and **Commit changes**.
4. Your existing Streamlit Cloud app should redeploy automatically at its current `.streamlit.app` address.
5. The **only required** secret in Streamlit Cloud Settings → Secrets is:

```toml
FOOTBALL_DATA_API_KEY = "your_private_football_data_org_token"
```

Keep the real key in Streamlit Cloud Secrets, **not** GitHub. `API_FOOTBALL_KEY` can stay in secrets but is not used by this version. Streamlit needs access to the original `app.py` at repository root.

Select an upcoming match and press **Load rosters + this-season player statistics**. The app may use several API calls on the first click; it is optimized for the free provider limit of 10 requests per minute, but other users/actions might cause a temporary 429. If so, wait and retry.

## Testing

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
python -m streamlit run app.py
```

In the development environment, **29 automated tests passed**, and Python syntax compiled. The Streamlit package was unavailable in the development runtime, so the complete UI couldn't be launched there. Live provider API calls require your private key and remain unverified until deployment. Tested code only; no guarantee of predictive accuracy or profitable bets.

## Sources / API documentation

- https://www.football-data.org/documentation/quickstart
- https://docs.football-data.org/general/v4/competition.html
- https://docs.football-data.org/general/v4/team.html

The displayed match results, club rosters and scorer totals are obtained from football-data.org. That is a recognized third-party sports data provider; this program does not independently audit each event against league match reports. It does not scrape sites such as FBref or Opta, nor bypass paywalls.
