# ⚽ Soccer AI Simulator V4.5.1 — automatic season-based strength model

La Liga, Premier League and UEFA Champions League Streamlit soccer simulator.

**V4.5.1 change:** The simulation count is fixed at **100,000** rather than 25,000; model predictions and data sources are otherwise unchanged.

**Major change:** No manual strength, home-advantage, baseline-goal, corner, or individual-scorer sliders. Choose a real scheduled fixture: the app loads this season's published match scores and generates goal and result estimates automatically. It uses **only the 2026–27 season** as of November 2026; the year updates each July.

## How it works

- Match results come from the season-filtered **football-data.org v4 API** (`/competitions/{code}/matches?season=2026`); the app does not invent scores or team histories.
- On opening a match the app requests, if available, the **Champions League, La Liga, Premier League, Bundesliga, Serie A and Ligue 1**. Six endpoint requests or fewer are needed on an initial launch. Results are cached for 30 minutes. If optional competitions are unavailable their failures are temporarily cached, and the model explains reduced coverage. Click Refresh in the sidebar to clear data caches.
- The automatic team strength model uses a **regularized opponent-adjusted Poisson goal model** fitted to reported match scores. It learns each team's attack and goals-conceded strength jointly, from **both its domestic and UCL matches**, connecting leagues through clubs playing across competitions.
- More recent matches get greater weight (75-day half-life). Small samples are shrunk toward an explicit league-average prior. The scoring baseline for each competition and aggregate home advantage are learned from the available season results with shrinkage.
- **A Greek-league-only club's Greek domestic games cannot be included** because the Greek Super League is not among the free covered leagues used here. For such clubs the model uses European match results and conservative priors, displays a reduced-data warning, and does **not** pretend to know a verified cross-league ranking. Portuguese/Dutch league results are not included in this six-feed default, to leave rate-limit headroom.
- The displayed "projected goals" are **model expectations based on past goals, NOT verified match xG**. Independent Poisson probabilities give home win/draw/away win and goal markets; 100,000 simulations supply scoreline frequencies automatically. No evidence of reliable gambling profits or superior accuracy is claimed.
- There is a **side-by-side historical backtest** for V4.4 and V4.5 on the *same* matches, with Brier and log loss computed using only fixtures from earlier calendar days (no same-day or future-data leakage). The new model could perform worse; inspect its scores before trusting it. Tests are within season and are *not* equivalent to third-party validation.
- Existing current-season partial player/scorer panels are kept. Click **Load rosters + this-season player statistics** for the free API's supported published goals/assists/penalty data. The scorer feed is a top-scorers list, not full minute/shots/xG/lineup information. Player goalscorer estimates are experimental.
- **Corners are not predicted** until an appropriate season corner-statistics provider is available; manual corners/sliders are removed rather than giving fabricated automatic numbers.

### Automatic sources and coverage

- Football-data.org API docs: https://www.football-data.org/documentation/quickstart
- Published free competition coverage: https://www.football-data.org/coverage
- Match resources and `season` filtering: https://docs.football-data.org/general/v4/competition.html

Football-data.org is a third-party data provider, not the actual competition governing body. The app does **not independently cross-verify** every score with an official league report. It doesn't scrape copyrighted or paywalled player xG/shot data.

## Update your existing Streamlit website

1. Unzip `soccer_ai_simulator_v4_5_1.zip` on your computer.
2. In your existing public GitHub repository `segov14/soccer-ai-simulator`, select **Add file → Upload files**, and upload **all project files from inside the extracted folder**, not the ZIP or a top-level wrapper folder. Overwrite the older versions and **Commit changes**.
3. Streamlit Community Cloud should automatically redeploy the existing app. Keep `app.py` in the repository root.
4. Your existing private Streamlit Secrets entry must contain:

```toml
FOOTBALL_DATA_API_KEY = "your_key_here"
```

5. **Never** upload the real key to GitHub or send it in chat. `API_FOOTBALL_KEY` is not needed for this version.
6. Select a competition, then a scheduled match. The model calculates the strengths and probabilities automatically. Optional data feeds may be unavailable on your plan or occasionally hit football-data.org's free rate limit of 10 requests/minute.

## Tests

Run locally:

```sh
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
python -m streamlit run app.py
```

The supplied build passed **36 automated tests**, compiled as valid Python, and verified the downloaded ZIP's files. The full Streamlit app launch was not tested in the build environment (Streamlit package unavailable and network access blocked), and the private API key was not used for a live connection. After deployment, please verify both fixture predictions and player results.

**Interpretation:** The new method is a research prototype, not trained on a sufficiently broad, independent evaluation dataset to be called accurate or reliable for placing bets. Use the app's Brier/log-loss comparison to determine whether predictions improve before treating them as credible.
