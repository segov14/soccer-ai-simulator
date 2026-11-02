# Soccer AI Simulator V3 — experimental predictions

Compatible with the same GitHub repository and Streamlit Cloud deployment as V2.

## Deploy

1. Upload every file in this ZIP **to the root of the existing GitHub repository**, replacing V2 files. Keep `app.py`, `model.py`, `advanced.py`, `requirements.txt` and tests at root.
2. Existing Streamlit Cloud app should redeploy automatically from the `main` branch and `app.py` entrypoint.
3. Keep `FOOTBALL_DATA_API_KEY = "..."` in **Streamlit Cloud > App settings > Secrets**, never in GitHub.
4. Confirm fixtures appear in each competition and try backtesting.

## What V3 does

- Calls football-data.org v4 every 30 minutes **when the site is active**; subject to your plan access.
- Ratings are derived from finished matches **within the selected competition**. This provides a common Champions League match basis, but **does not fully correct differences between domestic leagues**. Early-season and small-sample ratings may be unreliable.
- Displays analytic, exact Poisson 1X2 odds instead of Monte Carlo noise; simulated exact scores remain available.
- Offers chronological within-season historical backtesting (Brier score/log loss) without including same-day results when fitting match parameters. Not an independent multi-year validation and no cross-league calibration is claimed.
- Corner over/under and anytime-goalscorer estimates require **manually supplied assumptions** because the current provider data in this app lacks verified corner counts, player goal contributions, starting lineups and minutes. These panels are **NOT automatic real-data predictions**.
- Live lineups / scorer rankings / corners require a separate compatible provider and coverage verification; no paid API connection is included.

## Local run

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
python -m pytest -q
```

Set environment variable `FOOTBALL_DATA_API_KEY` for local live data. Do not put `.streamlit/secrets.toml` in GitHub.

## Limitations

Simple goals-based Poisson simulation, **not trained AI**, betting advice, injury model, true xG data or a guarantee of returns. It may be inaccurate. Backtest data depends on the matches returned by your provider API and is not a substitute for out-of-sample assessment across many seasons. Model does not model score correlation. Corner and player estimates are only as good as manually entered assumptions.
