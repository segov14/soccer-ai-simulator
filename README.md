# Soccer AI Simulator — Version 2

A mobile-friendly Streamlit app that pulls La Liga (`PD`), Champions League (`CL`), and Premier League (`PL`) match results and fixtures from football-data.org. It derives team attack / defense multipliers from completed games and performs 1,000–100,000 Monte Carlo soccer match simulations.

## Update your existing GitHub app

1. Unzip the package. **Upload its contents into the root of your existing `soccer-ai-simulator` GitHub repository** — not a parent folder. Replace `app.py`, `README.md`, `model.py`, `test_model.py`, and `requirements.txt`.
2. Ensure Streamlit Community Cloud points to `app.py` on the `main` branch.
3. On Streamlit Cloud, open the app menu → Settings → Secrets and add **exactly** this line, replacing the placeholder with your real token:
   ```toml
   FOOTBALL_DATA_API_KEY = "your-private-token"
   ```
   Never commit your token to GitHub, even in a private repository. You already may have this secret set, so don't duplicate it.
4. Commit your changes. Streamlit normally redeploys automatically. Refresh the app, choose a league, then choose a fixture. If necessary, reboot the app in Streamlit's Manage app menu.

## How automatic data works

- The app requests `GET https://api.football-data.org/v4/competitions/{PD|CL|PL}/matches` with an `X-Auth-Token` header.
- On page opening and when changing competitions it reads results/fixtures; successful responses are cached for **30 minutes**. Click **Refresh soccer data** to clear cached responses manually.
- Data are **refreshed on demand** when a visitor opens/uses the app; no always-on background scheduler is included.
- Only finished games contribute to estimates. Teams with fewer than three finished games use neutral multipliers (1.0). Team identity is based on API IDs rather than display names.
- Season availability, API quotas, and available competitions depend on the token's plan. If the provider rejects the request, a descriptive message appears. Use Manual / offline mode while troubleshooting.
- Projected goals are derived from simple historical goals-for/goals-against estimates and are **not actual xG data**.

## Local run

Install Python 3.11+, then from the directory containing `app.py`:

```bash
python -m pip install -r requirements.txt
# Set the API key as an environment variable, or provide .streamlit/secrets.toml locally (DO NOT commit secrets.toml)
python -m streamlit run app.py
```

## Prediction model and limitations

Independent Poisson simulated goal totals; home advantage 1.12 by default; shrinkage toward average team form. Outputs 1X2, total goals, BTTS and likely scores. **Not trained machine learning, a validated forecast, or guaranteed profitable betting advice.** No lineups, injuries, real xG feed, correlated scores or odds comparisons. Backtesting with chronological out-of-sample predictions is needed before assessing predictive accuracy.
