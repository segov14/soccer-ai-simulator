# Soccer Simulation Lab (prototype v0.1)

A functioning Streamlit soccer simulator for La Liga, UEFA Champions League, and Premier League. It runs 1,000–100,000 reproducible Monte Carlo draws with an independent Poisson goals model and displays 1X2 probabilities, over/under 2.5, both teams to score, and common scores.

## Run on your Windows PC (or Mac/Linux)

1. Install Python 3.11+ from python.org.
2. Unzip this folder and open a terminal in the `soccer_simulator` folder.
3. Run:

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Your browser opens the app. To stop: Ctrl+C. For Windows you may need `py -m pip ...` and `py -m streamlit ...`.

## Where the stats come from

- **Manual estimates**: offline and fully functional without signup. Example multipliers are illustrative, NOT actual team statistics. You can edit all four ratings for every matchup.
- **Optional API**: Create an API token at https://www.football-data.org/ . Select "Football-data.org API" and paste the token; the app downloads available completed matches and upcoming fixtures for the selected competition and estimates strength from goals scored/conceded with shrinkage. Free-plan coverage/rate limits vary; the API might not provide access to all historical match data. Fixture times are shown in UTC. Token is not bundled.

## Method

Given an attack multiplier A and a defense-conceded multiplier D, the projected home goals are `base_goals * home_attack * away_defense * home_advantage` and away goals are `base_goals * away_attack * home_defense / home_advantage`. For a neutral venue, advantage is 1. Each simulated side scores Poisson(lambda) goals. Probabilities are frequencies of results across N runs. This is a simplistic statistical model, NOT machine learning, and the default example inputs are hypothetical.

## Next steps toward a reliable product

- Historical results across multiple seasons; handle team promotions/name changes and cross-competition strength normalization.
- Proper attack/defense estimation (e.g. regularized Dixon–Coles/Poisson regression) and recent-game weighting.
- Add xG data, lineup/injury feeds (licensed data), rest, travel, and market odds.
- Backtest out-of-sample using rolling time splits. Measure log loss, Brier score, calibration, and performance vs closing odds **after bookmaker vig**.
- Add fixture refresh automation and mobile hosting (e.g. Streamlit Community Cloud). Protect any paid API keys in hosting secrets.

No guarantee of forecasting or profitable betting. This is a proof of concept.
