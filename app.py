"""Soccer AI Simulator V5 — real bookmaker prices and transparent model-based comparisons."""
from datetime import datetime, timezone
import os

import pandas as pd
import requests
import streamlit as st

from model import simulate
from advanced import exact_markets
from free_players import fetch_team_roster, RosterUnavailable
from strength import COMPETITIONS as MODEL_COMPETITIONS, fit_strength, project_goals, compare_backtest
from odds_data import (SPORT_KEYS, REGIONS, OddsUnavailable, odds_request, find_event,
                       compare_event, calibration_table)
from season_stats import (fetch_scorers, season_matches_only, team_totals_by_comp,
                          combine_player_rows, current_season_year, season_label,
                          StatsUnavailable, LEAGUES)

st.set_page_config(page_title="Soccer AI Simulator", page_icon="⚽", layout="wide")
COMPETITIONS = {"La Liga": "PD", "Champions League": "CL", "Premier League": "PL"}
SEASON_YEAR = current_season_year()
SEASON_NAME = season_label(SEASON_YEAR)
API_ROOT = "https://api.football-data.org/v4"


def get_token():
    """Cloud secret first; environment variable as local alternative."""
    try:
        secret = st.secrets.get("FOOTBALL_DATA_API_KEY", "")
    except (FileNotFoundError, KeyError):
        secret = ""
    return str(secret or os.getenv("FOOTBALL_DATA_API_KEY", "")).strip()


def get_odds_token():
    """Never render or log the private odds provider token."""
    try:
        secret = st.secrets.get("ODDS_API_KEY", "")
    except (FileNotFoundError, KeyError):
        secret = ""
    return str(secret or os.getenv("ODDS_API_KEY", "")).strip()


@st.cache_data(ttl=21600, show_spinner=False)
def load_market_odds(sport_key, secret_key, region, include_totals):
    """6-hour shared cache to conserve the free provider's monthly credits."""
    return odds_request(sport_key, secret_key, region, include_totals)


@st.cache_data(ttl=1800, show_spinner=False)
def load_matches(competition_code: str, api_token: str, season_year: int):
    """Request competition fixtures/results once per 30-minute cache period."""
    try:
        response = requests.get(
            f"{API_ROOT}/competitions/{competition_code}/matches",
            headers={"X-Auth-Token": api_token}, params={"season": int(season_year)}, timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.exceptions.HTTPError as error:
        status = error.response.status_code if error.response is not None else "unknown"
        if status == 429:
            raise ValueError("API request limit reached. Wait a minute and try Refresh data.") from error
        if status in (401, 403):
            raise ValueError("API token rejected or this competition isn't on your plan.") from error
        raise ValueError(f"Data provider returned HTTP {status}.") from error
    except (requests.RequestException, ValueError) as error:
        raise ValueError(f"Could not retrieve soccer data: {error}") from error

    finished, upcoming = [], []
    for m in payload.get("matches", []):
        h = m.get("homeTeam") or {}
        a = m.get("awayTeam") or {}
        # IDs are stable even when a team's display name changes.
        hname, aname = h.get("name"), a.get("name")
        if not hname or not aname or h.get("id") is None or a.get("id") is None:
            continue  # excludes TBD knockout participants
        item = {"home": hname, "away": aname, "hid": h["id"], "aid": a["id"],
                "date_utc": m.get("utcDate", ""), "id": m.get("id"), "stage": m.get("stage") or ""}
        score = (m.get("score") or {}).get("fullTime") or {}
        if m.get("status") == "FINISHED" and isinstance(score.get("home"), int) and isinstance(score.get("away"), int):
            finished.append({**item, "hg": score["home"], "ag": score["away"]})
        elif m.get("status") in ("SCHEDULED", "TIMED"):
            upcoming.append(item)
    finished, upcoming = season_matches_only(finished, upcoming, season_year)
    return finished, sorted(upcoming, key=lambda item: item["date_utc"])


@st.cache_data(ttl=86400, show_spinner=False)
def load_roster(team_id, api_token):
    return fetch_team_roster(team_id, api_token)


@st.cache_data(ttl=3600, show_spinner=False)
def load_scorers(code, api_token, season_year):
    return fetch_scorers(code, api_token, season_year)


@st.cache_data(ttl=120, show_spinner=False)
def load_optional_matches(competition_code, api_token, season_year):
    """Prevent repeated requests to unavailable competitions on each rerun."""
    try:
        results, _ = load_matches(competition_code, api_token, season_year)
        return results, None
    except ValueError as exc:
        return None, str(exc)


def readable_time(utc_string):
    try:
        return datetime.fromisoformat(utc_string.replace("Z", "+00:00")).astimezone().strftime("%b %d, %Y · %I:%M %p %Z")
    except (ValueError, AttributeError):
        return utc_string or "Date not announced"


st.title("⚽ Soccer AI Simulator · V5")
st.caption(f"La Liga · Champions League · Premier League | {SEASON_NAME} only · Automatic strengths + 100,000 simulations + real bookmaker odds · Experimental probabilities")

with st.sidebar:
    st.header("Automatic model")
    competition = st.selectbox("Competition", list(COMPETITIONS))
    st.caption("Team strengths, venue effects, scoring averages and the 100,000 simulation count are automatic. There are no manual strength sliders.")
    if st.button("↻ Refresh verified soccer data"):
        load_matches.clear()
        load_optional_matches.clear()
        load_scorers.clear()
        load_roster.clear()
        # Deliberately do not clear bookmaker-odds cache: refresh consumes quota.
        st.rerun()

api_token = get_token()
if not api_token:
    st.error("Configure FOOTBALL_DATA_API_KEY in Streamlit Secrets to load automatic predictions. No manual placeholder ratings are used.")
    st.stop()

code = COMPETITIONS[competition]
try:
    with st.spinner("Fetching current-season verified fixtures and results…"):
        finished, upcoming = load_matches(code, api_token, SEASON_YEAR)
except ValueError as exc:
    st.error(str(exc))
    st.stop()

if not upcoming:
    st.info("No upcoming scheduled fixtures are available for this competition. The app does not substitute invented matchups.")
    st.stop()

labels = [f"{readable_time(f['date_utc'])} — {f['home']} vs {f['away']}" for f in upcoming]
ix = st.selectbox("Choose an upcoming match", range(len(upcoming)), format_func=lambda i: labels[i])
selected = upcoming[ix]
home_name, away_name = selected['home'], selected['away']
home_key, away_key = str(selected['hid']), str(selected['aid'])
neutral = code == 'CL' and selected.get('stage') == 'FINAL'

# Every dataset comes from the football-data.org 2026/27 season-filtered
# official match-results endpoint. Cache prevents wasteful refresh polling.
# Limit the initial request batch to six (incl. requested competition) so the
# football-data.org free-plan ten/minute quota has some headroom for players.
MODEL_FEEDS = ['CL', 'PD', 'PL', 'BL1', 'SA', 'FL1']
results_by_code = {code: finished}
missing_codes = []
with st.spinner("Comparing opponent quality across current-season domestic and European fixtures…"):
    for extra in MODEL_FEEDS:
        if extra == code:
            continue
        try:
            prior, problem = load_optional_matches(extra, api_token, SEASON_YEAR)
            if problem:
                missing_codes.append(f"{MODEL_COMPETITIONS.get(extra, extra)}: {problem}")
            else:
                results_by_code[extra] = prior
        except Exception:
            missing_codes.append(f"{MODEL_COMPETITIONS.get(extra, extra)}: data not available")

fitted = fit_strength(results_by_code, as_of=selected.get('date_utc'))
projection = project_goals(fitted, selected['hid'], selected['aid'], code, neutral=neutral)
hxg, axg = projection['home_goals'], projection['away_goals']
n = 100000
pred = simulate(hxg, axg, n=n, seed=42)
exact = exact_markets(hxg, axg)

st.success(f"Provider-reported match score data: football-data.org · {SEASON_NAME} · {projection['n_matches']} completed games across {len(fitted['codes'])} available competitions · cache refresh roughly every 30 min on app activity")
if missing_codes:
    with st.expander("Unavailable competition feeds — coverage limitations"):
        for warning in missing_codes:
            st.write('• ' + warning)
if code == 'CL' and not any(c in results_by_code for c in ('PD', 'PL', 'BL1', 'SA', 'FL1')):
    st.warning("All domestic cross-league feeds were unavailable. This prediction is based on Champions League scores alone and is highly uncertain.")
st.caption("Free-data coverage modeled automatically: Champions League, La Liga, Premier League, Bundesliga, Serie A and Ligue 1 when accessible. Portuguese, Dutch and Greek domestic results are not fetched; corresponding teams have less reliable strength estimates.")

st.subheader(f"{home_name} vs {away_name}")
st.caption("**Automatic strengths:** Provider-reported goals scored/conceded, opponent quality, recent results, home/away effect and UCL-to-domestic links. These are model-based scoring means, NOT measured xG, and are not calibrated betting odds. [Source and API documentation](https://www.football-data.org/documentation/quickstart)")

ca, cb = st.columns(2)
for panel, label, side in [(ca, home_name, 'home'), (cb, away_name, 'away')]:
    rating = projection[side + '_rating']
    with panel:
        st.markdown('**' + label + '**')
        st.caption(projection[side + '_quality'])
        if rating:
            st.metric('2026–27 matches in model', rating['games'])
            st.write(f"Attack multiplier **{rating['attack']:.2f}×** · Conceded-goals multiplier **{rating['defense_conceded']:.2f}×**")
            st.caption('Data used: ' + ', '.join(f"{MODEL_COMPETITIONS.get(c,c)} ({v})" for c,v in rating['by_competition'].items()))
        else:
            st.write('No verified season results for this club. Neutral league-average prior used.')
if code == 'CL' and ((projection['home_rating'] or {}).get('domestic_games', 0) == 0 or (projection['away_rating'] or {}).get('domestic_games', 0) == 0):
    st.warning("At least one club has no domestic results in the supported feeds. The model uses its European matches and conservative defaults; cross-league strength is uncertain.")

m1, m2, m3 = st.columns(3)
m1.metric(f"{home_name} win", f"{exact['home_win']:.1%}")
m2.metric('Draw', f"{exact['draw']:.1%}")
m3.metric(f"{away_name} win", f"{exact['away_win']:.1%}")
st.caption(f"Model-projected goals: {home_name} **{hxg:.2f}**, {away_name} **{axg:.2f}** · Home advantage derived from available season results (ratio {fitted['home_ratio']:.2f})" + (" · Neutral venue modeled" if neutral else ""))
st.caption("1X2 percentages are exact independent-Poisson calculations, not Monte Carlo estimates. 100,000 score simulations run automatically for scoreline distributions.")
left, right = st.columns(2)
with left:
    st.subheader("1X2 probabilities")
    st.bar_chart(pd.DataFrame({'Probability': [exact['home_win'], exact['draw'], exact['away_win']]}, index=['Home win', 'Draw', 'Away win']))
with right:
    st.subheader("Goals markets")
    st.bar_chart(pd.DataFrame({'Probability': [exact['over_25'], exact['under_25'], exact['btts']]}, index=['Over 2.5', 'Under 2.5', 'Both score']))
st.subheader("Most likely exact scores")
st.dataframe(pd.DataFrame(pred['scores'], columns=['Score (home-away)', 'Probability']).style.format({'Probability': '{:.1%}'}), hide_index=True, use_container_width=True)

st.divider()
st.subheader("💹 V5 · Real bookmaker odds vs. model")
st.caption("Odds source: [The Odds API](https://the-odds-api.com/) (recent bookmaker quotes); model source: football-data.org season match results. The model's probabilities are **NOT proven calibrated**. Rankings below show mathematical disagreements, not verified profitable bets or recommendations.")
odds_token = get_odds_token()
if not odds_token:
    st.info("Add ODDS_API_KEY in Streamlit Secrets to enable bookmaker comparisons. Your match predictions continue working without it.")
else:
    region_ui, totals_ui = st.columns([1, 2])
    with region_ui:
        region_name = st.selectbox("Bookmaker region", list(REGIONS), index=0,
                                   help="Only one region is queried at a time to conserve API credits.")
    with totals_ui:
        add_totals = st.checkbox("Also request Over/Under 2.5 odds", value=False,
                                 help="May cost 1 additional credit each time odds are fetched. Soccer totals coverage depends on bookmaker.")
    st.caption("The free Odds API quota is limited. A 1X2 request in one region normally costs 1 credit; adding totals can cost 1 more. Quotes are cached up to 6 hours, so they may be stale. Switches and manual refreshes can spend additional credits.")
    if st.button("↻ Refresh bookmaker odds (uses API credits)", key="refresh_odds"):
        load_market_odds.clear()
        st.rerun()
    try:
        with st.spinner("Retrieving available bookmaker odds…"):
            odds_result = load_market_odds(SPORT_KEYS[code], odds_token, REGIONS[region_name], add_totals)
        quota = odds_result['quota']
        quota_label = (f" · {quota['x-requests-remaining']} API credits remaining"
                       if quota.get('x-requests-remaining') is not None else "")
        st.caption(f"Last fetched from provider (UTC): {odds_result['retrieved_utc']}{quota_label}")
        odds_match = find_event(odds_result['events'], home_name, away_name, selected['date_utc'])
        if odds_match is None:
            st.info("No confidently matched bookmaker odds for this exact fixture, region, and kickoff. An empty market is not a zero-probability event. Try another region or refresh near matchday.")
        else:
            st.write(f"**Matched market:** {odds_match.get('home_team')} vs. {odds_match.get('away_team')} · {readable_time(odds_match.get('commence_time'))}")
            model_p = {'home_win': exact['home_win'], 'draw': exact['draw'],
                       'away_win': exact['away_win'], 'over_25': exact['over_25'],
                       'under_25': exact['under_25']}
            quotes = compare_event(odds_match, model_p, odds_result['retrieved_utc'])
            if not quotes:
                st.info("This fixture has no complete full-time 1X2 market or available 2.5-goal total from this region. Two-outcome soccer moneylines are intentionally excluded.")
            else:
                weak = ('Limited' in projection['home_quality'] or 'Limited' in projection['away_quality']
                        or 'Unavailable' in projection['home_quality'] or 'Unavailable' in projection['away_quality']
                        or 'Very limited' in projection['home_quality'] or 'Very limited' in projection['away_quality'])
                if weak:
                    st.warning("At least one team has limited historical results. Model differences should not be interpreted as reliable betting value.")
                st.caption("No-vig market probability normalizes each bookmaker's complete 1X2 (or Over/Under) prices separately. Model EV = (model probability × decimal odds − 1) × 100%. A positive number is **only a hypothetical model estimate**; it does not establish a real edge.")
                quotes_df = pd.DataFrame(quotes)
                cols = ['Market', 'Outcome', 'Bookmaker', 'Decimal odds', 'American odds',
                        'Model probability', 'Raw implied probability', 'No-vig market probability',
                        'Model-market edge (pp)', 'Model EV ROI (%)',
                        'Odds last updated (UTC)']
                display = quotes_df[cols].head(40).copy()
                for key in ('Model probability', 'Raw implied probability', 'No-vig market probability'):
                    display[key] = display[key].map(lambda v: f'{v:.1%}')
                for key in ('Model-market edge (pp)', 'Model EV ROI (%)'):
                    display[key] = display[key].map(lambda v: f'{v:+.1f}')
                display['Decimal odds'] = display['Decimal odds'].map(lambda v: f'{v:.2f}')
                st.dataframe(display, hide_index=True, use_container_width=True)
                st.caption("Sorted by estimated model EV, not reliability. These are not verified profitable opportunities. Prices can change or be unavailable to you; no betting is performed.")
                prediction_csv = quotes_df.copy()
                prediction_csv['Match'] = f"{home_name} vs {away_name}"
                prediction_csv['Competition'] = competition
                prediction_csv['Season'] = SEASON_NAME
                prediction_csv['Home quality'] = projection['home_quality']
                prediction_csv['Away quality'] = projection['away_quality']
                st.download_button("Download bookmaker/model comparison CSV (one snapshot)",
                                   prediction_csv.to_csv(index=False).encode('utf-8'),
                                   f"v5_odds_snapshot_{SEASON_YEAR}.csv", "text/csv")
                st.caption("CSV snapshots must be saved by you; Streamlit does not maintain a permanent betting-results log across redeployments.")
    except OddsUnavailable as exc:
        st.warning(f"Bookmaker odds unavailable: {exc} Other predictions are unaffected.")

st.divider()
st.subheader('🚩 Corners — automatic data not available')
st.info('The currently configured verified free API does not provide usable season corner counts. No corner probabilities or manual estimates will be shown until a permitted, reliable data feed is connected.')

st.divider()
st.subheader(f"👥 {SEASON_NAME} player stats & experimental anytime-scorer chances")
st.caption("Verified source: football-data.org v4 season-filtered top-scorers feed (goals, assists, penalties) plus current squads and completed matches. These are NOT comprehensive individual player logs or confirmed starters.")
selected_match = selected
if selected_match:
    st.caption("Official scorer totals refresh at most hourly; rosters are cached for 24 hours. Missing players are not assumed to have zero goals.")
    if st.button("🔎 Load rosters + this-season player statistics"):
        st.session_state["player_stats_match_loaded"] = (competition, selected_match["id"], SEASON_YEAR)
    if st.session_state.get("player_stats_match_loaded") == (competition, selected_match["id"], SEASON_YEAR):
        all_results = {COMPETITIONS[competition]: finished}
        scorer_by_comp = {}
        issues = []
        with st.spinner("Loading published scorer feeds and this-season club results…"):
            for scorer_code in LEAGUES:
                try:
                    rows, maybe_truncated = load_scorers(scorer_code, api_token, SEASON_YEAR)
                    scorer_by_comp[scorer_code] = rows
                    if maybe_truncated:
                        issues.append(f"{LEAGUES[scorer_code]} may be truncated at its top-scorer API limit.")
                except StatsUnavailable as exc:
                    issues.append(str(exc))
                if scorer_code not in all_results:
                    try:
                        other_finished, _ = load_matches(scorer_code, api_token, SEASON_YEAR)
                        all_results[scorer_code] = other_finished
                    except ValueError as exc:
                        issues.append(f"{LEAGUES[scorer_code]} result data unavailable for shares: {exc}")
        totals = team_totals_by_comp(all_results)
        if not scorer_by_comp:
            st.warning("Current-season scorer data is unavailable with your API access. We will display rosters, but no player-specific probabilities.")
        if issues:
            with st.expander("API coverage and missing-data notices"):
                for issue in issues:
                    st.write("• " + issue)
        for name, tid in [(home_name, selected_match["hid"]), (away_name, selected_match["aid"])]:
            st.markdown(f"### {name} — {SEASON_NAME} player overview")
            try:
                roster = load_roster(tid, api_token)
            except RosterUnavailable as error:
                st.info(str(error))
                roster = []
            if roster:
                team_mean = hxg if tid == selected_match["hid"] else axg
                rows = combine_player_rows(roster, tid, scorer_by_comp, totals, team_mean)
                sample_size = sum(r["Anytime chance (experimental)"] is not None for r in rows)
                c_a, c_b, c_c = st.columns(3)
                c_a.metric("Squad members", len(rows))
                c_b.metric("With published scorer records", sum(r["Goals"] is not None for r in rows))
                c_c.metric("With experimental estimates", sample_size)
                frame = pd.DataFrame(rows)
                frame["Anytime chance (experimental)"] = frame["Anytime chance (experimental)"].map(
                    lambda prob: f"{prob:.1%}" if prob is not None else "No verified player scoring data")
                st.dataframe(frame.drop(columns=["Source URLs", "Season"]), hide_index=True, use_container_width=True)
                st.download_button(f"Download {name} current-season player stats CSV",
                                   frame.to_csv(index=False).encode("utf-8"),
                                   f"team_stats_{tid}_{SEASON_YEAR}.csv", "text/csv", key=f"team_csv_{tid}_{SEASON_YEAR}")
                st.caption("The same position does NOT mean the same percentage: estimates now depend on that player's reported goals divided by goals scored by their team in the same published competitions. Missing scorer records = unknown, not zero.")
            else:
                st.info("The provider did not return a squad for this team.")
        if scorer_by_comp:
            with st.expander(f"📈 Overall {SEASON_NAME} scorer-feed leaders (all 3 competitions)"):
                combined = {}
                for leaderboard_code, rows in scorer_by_comp.items():
                    for r in rows:
                        identity = (r["id"] if r["id"] is not None else r["name"], r["team_id"])
                        entry = combined.setdefault(identity, {"Player": r["name"], "Team": r["team"], "Goals": 0,
                                  "Assists": 0, "Penalties": 0, "Goals leagues": [], "_missing_assists": False, "_missing_penalties": False})
                        entry["Goals"] += r["goals"]
                        if r["assists"] is not None:
                            entry["Assists"] += r["assists"]
                        else:
                            entry["_missing_assists"] = True
                        if r["penalties"] is not None:
                            entry["Penalties"] += r["penalties"]
                        else:
                            entry["_missing_penalties"] = True
                        entry["Goals leagues"].append(LEAGUES[leaderboard_code])
                summary = sorted(combined.values(), key=lambda r: -r["Goals"])
                if summary:
                    for r in summary:
                        r["Goals leagues"] = ", ".join(r["Goals leagues"])
                        if r.pop("_missing_assists"):
                            r["Assists"] = None
                        if r.pop("_missing_penalties"):
                            r["Penalties"] = None
                    st.dataframe(pd.DataFrame(summary), hide_index=True, use_container_width=True)
                    st.download_button("Download current-season published scorer overview CSV",
                                       pd.DataFrame(summary).to_csv(index=False).encode("utf-8"),
                                       f"published_scorers_{SEASON_YEAR}.csv", "text/csv")
                st.caption("Partial top-scorer feed; NOT an exhaustive all-player statistics table. All totals come only from this season's available PL, La Liga and Champions League scorer endpoints. Missing assists or penalties are not necessarily zero.")
        st.warning("Experimental estimates only: a player's current-season goal SHARE is applied to this match's projected team goals using 1 − exp(−team goals × share). No verified playing minutes, shots, expected goals, injury information, or lineup participation are available from these free endpoints. This is not a validated anytime-goalscorer betting probability.")
        st.markdown("Data: [football-data.org API documentation](https://www.football-data.org/documentation/quickstart) · [scorers API reference](https://docs.football-data.org/general/v4/competition.html)")
else:
    st.info("Choose an upcoming match from the live fixtures to load the current-season scorer reports for both squads.")

if len(finished) >= 25:
    st.divider()
    st.subheader("🧪 Historical rolling backtest")
    st.caption("For each past fixture, both models are trained only on earlier calendar days from this season. We compare their out-of-sample errors; a new model can score worse.")
    if st.button("Compare models on past fixtures"):
        backtest = compare_backtest(results_by_code, code)
        if backtest:
            df = pd.DataFrame(backtest)
            st.metric("Past matches tested (no same-day result leakage)", len(df))
            st.dataframe(pd.DataFrame([
                {'Model': 'Previous V4.4', 'Mean Brier': df['V4.4 Brier'].mean(), 'Mean log loss': df['V4.4 log loss'].mean()},
                {'Model': 'New V4.5', 'Mean Brier': df['V4.5 Brier'].mean(), 'Mean log loss': df['V4.5 log loss'].mean()}
            ]).style.format({'Mean Brier':'{:.3f}', 'Mean log loss':'{:.3f}'}), hide_index=True)
            st.dataframe(df, hide_index=True, use_container_width=True)
            st.download_button("Download comparable backtest CSV", df.to_csv(index=False).encode(), 'v45_backtest.csv', 'text/csv')
            st.caption("Lower loss is better. New model may perform worse. Neither model is proven calibrated; only earlier-dated matches were used to predict each fixture.")
            reliability = calibration_table(backtest)
            if reliability:
                st.markdown("**V5 reliability diagnostic — preliminary, not a fitted calibration curve**")
                bins_df = pd.DataFrame(reliability)
                st.dataframe(bins_df.style.format({'Mean predicted': '{:.1%}', 'Observed frequency': '{:.1%}'}),
                             hide_index=True, use_container_width=True)
                st.caption("Observed frequencies are based only on recent held-out match outcomes; each match contributes home/draw/away observations. Sample sizes are usually too small for dependable calibration. No calibration adjustment is applied to odds comparisons.")
        else:
            st.info("Not enough earlier match results to compare models without future-data leakage.")
else:
    st.caption("Historical backtest available when a competition has at least 25 completed API fixtures.")

report = pd.DataFrame([{"competition": competition, "home": home_name, "away": away_name,
                        "projected_home_goals": hxg, "projected_away_goals": axg, "home_win": exact["home_win"],
                        "draw": exact["draw"], "away_win": exact["away_win"], "over_2_5": exact["over_25"],
                        "both_score": exact["btts"], "simulations": n,
                        "data_source": "football-data.org season results", "season": SEASON_NAME}])
st.download_button("Download prediction CSV", report.to_csv(index=False).encode(), "soccer_prediction.csv", "text/csv")
st.caption(f"Important: {SEASON_NAME} only. Real prices from The Odds API; bookmaker odds and model outcomes are compared but the prediction model is not validated or calibrated. Strength ratings use official provider-reported match scores and regularized opponent-adjusted Poisson estimates, not measured xG. Cross-league comparisons are connected through UEFA matches where available, but not externally calibrated. Player statistics are partial scorer-feed totals; scorer probabilities are experimental and do not account for confirmed lineups, injuries, minutes or shots. Corners are unavailable without verified data. Backtest comparisons, not simulated counts, indicate prediction performance. Refresh requires app activity.")
