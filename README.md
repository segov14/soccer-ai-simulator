# Soccer AI Simulator V4.1 — Free Roster Edition

Streamlit app for match simulations in La Liga, Champions League, and Premier League.

## What's new

- Retrieves team rosters from the same football-data.org API already used for match results (`GET /v4/teams/{team_id}`).
- No longer attempts to use the restricted API-Football current-season fixtures/lineup/player endpoints.
- Roster lists clearly state **squad members, not confirmed starters**. If access is restricted, the app displays a friendly unavailable message rather than failing.
- Automatic goalscorer probabilities are **disabled** because rosters alone cannot establish likely participation or player goalscoring rates. The optional manual assumption-based scorer calculator remains available.
- All original match simulations, corners (manual assumptions) and historical backtesting remain in place.

## Deploy

Upload the extracted project files to the repository root on GitHub, replacing existing files. Streamlit Community Cloud should redeploy from your existing repository.

Streamlit Secrets only needs:

```toml
FOOTBALL_DATA_API_KEY = "your_private_key"
```

`API_FOOTBALL_KEY` can remain in Streamlit Secrets but **is not used** in V4.1. Never commit secrets or keys to GitHub.

## Test

```bash
python -m pip install -r requirements.txt
python -m unittest discover -p 'test_*.py'
streamlit run app.py
```

### Limitations

Available roster names may not be current or included in the free football-data.org plan. No official lineups, current player scoring stats, or verified corner data are implied. The simulator's result probabilities are experimental and not demonstrated to provide a betting edge.
