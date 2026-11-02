# ⚽ Soccer AI Simulator — Version 5 (Bookmaker Odds + Value Analysis)

A Streamlit web app for **La Liga, the UEFA Champions League and Premier League**. This release builds on V4.5.1 (fixed **100,000** simulated scorelines, automatically fitted current-season team strengths, published player stats and rolling backtests). It adds real bookmaker prices from [The Odds API](https://the-odds-api.com/) for comparing model estimates with the market.

## New in V5

1. **Automatic bookmaker odds:** The app retrieves available prices for the selected competition and bookmaker region. Default: US region; 90-minute **three-way 1X2** markets only (home, draw, away). Optionally request **Over/Under 2.5** prices when supplied by sportsbooks. **Prices are not invented when absent.**
2. **Safe fixture matching:** It matches both teams and approximate kickoff time against the football-data.org fixture. Ambiguous matches, missing draw odds and wrong markets are not compared.
3. **No-vig probabilities:** Each bookmaker's complete 3-way market is normalized separately. Comparison includes raw implied chance, no-vig chance, our model probability, and their difference in percentage points.
4. **Hypothetical expected value (EV):** The app calculates `100 × (model_probability × decimal_odds − 1)` (percent ROI). The estimated return on a $100 hypothetical stake is the **same numeric amount in dollars**. These are **only consequences of the model's assumed probabilities**, not validated winning edges or recommendations.
5. **Quote auditability:** Show the bookmaker name, decimal and American quotes, sportsbook update time, retrieval timestamp, and API credits remaining when supplied. Download a timestamped CSV snapshot for recordkeeping.
6. **Basic reliability diagnostic:** The old V4.4 vs V4.5 rolling backtest now also displays a preliminary five-bin probability-vs-result table. This is **NOT a calibrated forecast**, and V5 does *not* apply any calibration adjustments without sufficient prospective evidence.
7. **Free-tier conservation:** API results are cached for up to **six hours**. Refreshing odds manually or switching region/market can consume more credits. The free Odds API plan is currently listed as 500 credits/month; check your provider dashboard. Changing a soccer data cache does **not** automatically clear the odds cache.

## Install into your existing GitHub + Streamlit app

1. Download and extract the V5 ZIP archive.
2. In your repository `segov14/soccer-ai-simulator`, choose **Add file → Upload files**. Drag **the extracted files themselves**, including `app.py` and the new `odds_data.py`, into the **repository root**, not the ZIP or a wrapper folder. Commit the files, replacing older versions.
3. Your existing Streamlit deployment should redeploy from `main` → `app.py` after GitHub updates.
4. In [Streamlit Community Cloud](https://share.streamlit.io/), open the app's **Settings → Secrets** and keep your two private keys in valid TOML form:

```toml
FOOTBALL_DATA_API_KEY = "your_football_data_org_key"
ODDS_API_KEY = "your_the_odds_api_key"
```

**Never** paste real API keys in GitHub or chat. `API_FOOTBALL_KEY` is not used in this release.

5. Open your app, choose an upcoming fixture and inspect the **V5 Real bookmaker odds vs model** panel. US, Europe and UK are **alternative regions**; each may offer different or no prices. **By default h2h only** costs 1 credit per refresh per region; adding totals may cost another. The actual credits used/remaining are returned by the provider.
6. If a match has no bookmakers, see the availability note. Odds are usually published closer to kickoff and aren't guaranteed in a particular region. Prices may change between refreshes. If quota is exhausted, wait for the provider reset or adjust usage; other soccer predictions can still work.

## Sources & model limitations

- **Match results, season-roster data, and season scorer feeds:** [football-data.org](https://www.football-data.org/documentation/quickstart). Fitted team strengths come only from available **current-season** results across CL, PD, PL, BL1, SA and FL1. The model is a regularized opponent-adjusted Poisson model fitted to match scores. 'Projected goals' are **not measured xG**. Champions League clubs whose domestic-league data is missing are flagged as less certain.
- **Bookmaker odds:** [The Odds API v4](https://the-odds-api.com/liveapi/guides/v4/) using `soccer_spain_la_liga`, `soccer_uefa_champs_league` and `soccer_epl`. Real moneyline market requires three outcomes. The Odds API includes timestamps and remaining quotas when available.
- **No betting is executed:** The app does not know your state's sportsbook eligibility, whether you can place the displayed quote, limits, transaction costs, or whether a stale quote is still available.
- **Uncalibrated forecasts:** More Monte Carlo simulations only reduce simulation noise. Neither the scores model nor its apparent edges are proven calibrated. To determine real predictive or betting value, save *pre-match* odds/probability snapshots over many games, then assess out-of-sample log loss, Brier score, calibration, and realized results before any claims of profitability.
- **No permanent prediction history:** Streamlit Community Cloud's runtime isn't a durable database. CSV snapshots can be downloaded manually. A proper prediction-logging database and automated post-match settlement are a later upgrade.
- **Unavailable advanced data:** Current free feeds do not guarantee live injuries, lineups, player xG, minutes or corner statistics. Experimental player probabilities are estimates from partial top-scorer feeds. Corners remain disabled until quality-assured data is available.

## Run and test locally

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
python -m streamlit run app.py
```

Live provider calls cannot be tested without your secret keys; the included tests use synthetic sample responses and do **not** imply that bookmakers will return odds for every match or that model edges are accurate.
