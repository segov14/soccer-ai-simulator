# Soccer AI Simulator V4 — automatic player lookup

## Deploy on your existing Streamlit site

1. Extract this ZIP, and upload **all files inside it** to the **root** of your existing `segov14/soccer-ai-simulator` GitHub repository. Replace the older files, and commit changes to the same branch Streamlit uses.
2. In **Streamlit Cloud → app settings → Secrets**, retain your existing key and configure the new one (do not commit it to GitHub):

```toml
FOOTBALL_DATA_API_KEY = "your_existing_key"
API_FOOTBALL_KEY = "your_api_football_key"
```

3. Let Streamlit redeploy, then choose a competition and an upcoming match. Click **Load players for this match** in the new player panel. API-Football data is fetched only on demand to conserve the free plan's request quota.
4. If an error indicates the endpoint/season is unavailable, check your API-Football subscription's supported seasons. The free plan may not have current 2026/27 data.

## What's new

- Resolves the selected football-data.org fixture to an API-Football fixture by competition, date and team names. **Will not guess if resolution is uncertain.**
- Loads **confirmed lineups where available** and shows the squad otherwise (clearly marked **NOT confirmed or predicted starters**).
- Uses available player season goals and minutes to produce **illustrative** anytime goalscorer probabilities **only when a lineup and player statistics exist**. These are rough proportional estimates, not calibrated real-player xG forecasts; first page only, so incomplete data possible. Treat missing players as unavailable, never as zero-quality players.
- Matches and API-Football resources are cached; no automatic polling of advanced data and no guarantee of availability on the free plan. Existing football-data.org fixtures refresh while the app is active approximately every 30 min.
- Preserves V3 simulation, Poisson result odds, manual corners, optional manual player estimates and backtesting.

## Limitations

**Corners remain manual**, since no validated automated corners model has been added. API-Football free plans and competition coverage vary. Squads do not imply playing time. Lineups may arrive shortly before kickoff, or later. API-Football IDs are not interchangeable with football-data.org IDs. The player probabilities are illustrative, not validated betting forecasts. The simulator still lacks proper calibrated cross-league team quality, player xG, injuries, venue-specific player modeling and independently validated corner predictions.

## Local development

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
python -m pytest -q
```

Set `FOOTBALL_DATA_API_KEY` and `API_FOOTBALL_KEY` as environment variables for local runs. `pytest` is required only for testing; install it separately. Don't add any key to `.py` files, committed TOML, `.env`, or GitHub.
