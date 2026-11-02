"""Soccer Simulation Lab v3 — auto-loaded fixtures and results."""
from datetime import datetime, timezone
import os

import pandas as pd
import requests
import streamlit as st

from model import expected_goals, simulate, rating_from_results
from advanced import exact_markets, corner_markets, anytime_scorer, rolling_backtest
from free_players import fetch_team_roster, RosterUnavailable
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
                "date_utc": m.get("utcDate", ""), "id": m.get("id")}
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


def readable_time(utc_string):
    try:
        return datetime.fromisoformat(utc_string.replace("Z", "+00:00")).astimezone().strftime("%b %d, %Y · %I:%M %p %Z")
    except (ValueError, AttributeError):
        return utc_string or "Date not announced"


st.title("⚽ Soccer AI Simulator · V4.4")
st.caption(f"La Liga · Champions League · Premier League | {SEASON_NAME} ONLY · Verified provider-reported goal totals · Experimental predictions")

with st.sidebar:
    st.header("Settings")
    competition = st.selectbox("Competition", list(COMPETITIONS))
    n = st.select_slider("Monte Carlo simulations", [1000, 5000, 10000, 25000, 50000, 100000], value=25000)
    seed = st.number_input("Random seed", min_value=0, max_value=1000000, value=42)
    neutral = st.checkbox("Neutral venue", value=False)
    manual = st.toggle("Manual / offline mode", value=False,
                       help="Use your own team names and strength ratings without the API.")
    if st.button("↻ Refresh soccer data"):
        load_matches.clear()
        load_scorers.clear()
        load_roster.clear()
        st.rerun()

finished, upcoming, ratings = [], [], {}
base_goals = 1.35
api_token = get_token()
use_live = bool(api_token) and not manual

if not api_token and not manual:
    st.warning("No API secret configured. Add FOOTBALL_DATA_API_KEY to your Streamlit deployment's Secrets, or enable Manual / offline mode.")
elif use_live:
    try:
        with st.spinner("Loading the latest competition results and fixtures…"):
            finished, upcoming = load_matches(COMPETITIONS[competition], api_token, SEASON_YEAR)
        # Build ratings using the same team IDs, not potentially inconsistent names.
        rating_matches = [{"home": str(m["hid"]), "away": str(m["aid"]), "hg": m["hg"], "ag": m["ag"]} for m in finished]
        ratings, base_goals = rating_from_results(rating_matches)
        st.success(f"Auto-data connected · {SEASON_NAME} season · {len(finished)} completed matches · {len(upcoming)} upcoming matches · refreshed approximately every 30 minutes")
    except ValueError as exc:
        st.error(str(exc))
        st.info("You can still use Manual / offline mode in the sidebar.")
        use_live = False

if use_live and upcoming:
    labels = [f"{readable_time(f['date_utc'])} — {f['home']} vs {f['away']}" for f in upcoming]
    ix = st.selectbox("Choose an upcoming match", range(len(upcoming)), format_func=lambda i: labels[i])
    selected = upcoming[ix]
    home_name, away_name = selected["home"], selected["away"]
    home_key, away_key = str(selected["hid"]), str(selected["aid"])
else:
    if use_live and not upcoming:
        st.info("No upcoming fixtures were returned for this competition. You can enter a matchup manually below.")
    c1, c2 = st.columns(2)
    with c1:
        home_name = st.text_input("Home team", value="Real Madrid")
    with c2:
        away_name = st.text_input("Away team", value="Barcelona")
    home_key, away_key = None, None

fallback = {"attack": 1.0, "defense": 1.0, "games": 0}
hr = ratings.get(home_key, fallback)
ar = ratings.get(away_key, fallback)
if use_live and upcoming and (hr["games"] == 0 or ar["games"] == 0):
    st.warning("At least one team has fewer than 3 completed matches. League-average ratings are used where data is insufficient.")

st.subheader(f"{home_name or 'Home'} vs {away_name or 'Away'}")
st.caption("Strength estimates are based on goals scored and conceded, not actual xG. You can change any assumption.")

cols = st.columns(4)
ha = cols[0].number_input("Home attack", 0.4, 2.0, round(hr["attack"], 2), 0.05, key=f"ha_{competition}_{home_key}_{away_key}")
hd = cols[1].number_input("Home defense", 0.4, 2.0, round(hr["defense"], 2), 0.05, key=f"hd_{competition}_{home_key}_{away_key}")
aa = cols[2].number_input("Away attack", 0.4, 2.0, round(ar["attack"], 2), 0.05, key=f"aa_{competition}_{home_key}_{away_key}")
ad = cols[3].number_input("Away defense", 0.4, 2.0, round(ar["defense"], 2), 0.05, key=f"ad_{competition}_{home_key}_{away_key}")

c1, c2 = st.columns(2)
base = c1.slider("League-average goals per team", 0.7, 2.2, float(round(min(2.2, max(0.7, base_goals)), 2)), 0.05)
adv = c2.slider("Home advantage multiplier", 1.0, 1.4, 1.12, 0.01, disabled=neutral)

hxg, axg = expected_goals(ha, hd, aa, ad, base, adv, neutral)
pred = simulate(hxg, axg, n=n, seed=int(seed))
exact = exact_markets(hxg, axg)
a, b, c = st.columns(3)
a.metric(f"{home_name} win", f"{exact['home_win']:.1%}")
b.metric("Draw", f"{exact['draw']:.1%}")
c.metric(f"{away_name} win", f"{exact['away_win']:.1%}")
st.caption("Win/draw/loss uses exact Poisson probabilities, avoiding Monte Carlo sampling noise. Simulated scorelines remain below.")
st.caption(f"Projected goals: {home_name} {hxg:.2f} · {away_name} {axg:.2f} | {n:,} simulated games")

left, right = st.columns(2)
with left:
    st.subheader("1X2 probabilities")
    st.bar_chart(pd.DataFrame({"Probability": [pred["home_win"], pred["draw"], pred["away_win"]]}, index=["Home win", "Draw", "Away win"]))
with right:
    st.subheader("Goals markets")
    st.bar_chart(pd.DataFrame({"Probability": [pred["over_25"], pred["under_25"], pred["btts"]]}, index=["Over 2.5", "Under 2.5", "Both score"]))

st.subheader("Most likely exact scores")
st.dataframe(pd.DataFrame(pred["scores"], columns=["Score (home-away)", "Probability"]).style.format({"Probability": "{:.1%}"}), hide_index=True, use_container_width=True)


st.divider()
st.subheader("📊 Corners — assumption-based model")
st.warning("football-data.org does not supply verified corner averages through this app. Values below are MANUAL assumptions, not automatically calculated match predictions. Change them using a reliable source.")
with st.expander("Enter corner averages and estimate over/under lines", expanded=False):
    ca, cb = st.columns(2)
    hc = ca.number_input(f"{home_name} expected corners (your estimate)", 0.0, 20.0, 5.0, 0.1)
    ac = cb.number_input(f"{away_name} expected corners (your estimate)", 0.0, 20.0, 4.5, 0.1)
    if st.button("Calculate corner estimates"):
        cr = corner_markets(hc, ac)
        st.metric("Expected total corners", f"{cr['expected_total']:.1f}")
        st.dataframe(pd.DataFrame([{"Line": line, "Chance": cr[key]} for line, key in
            [("Over 7.5", "over_75"), ("Over 8.5", "over_85"), ("Over 9.5", "over_95"), ("Over 10.5", "over_105")]]).style.format({"Chance":"{:.1%}"}), hide_index=True)
        st.caption("Simple independent Poisson corner model. Not validated against corner statistics.")

st.divider()
st.subheader(f"👥 {SEASON_NAME} player stats & experimental anytime-scorer chances")
st.caption("Verified source: football-data.org v4 season-filtered top-scorers feed (goals, assists, penalties) plus current squads and completed matches. These are NOT comprehensive individual player logs or confirmed starters.")
selected_match = selected if use_live and upcoming else None
if selected_match:
    st.caption("Official scorer totals refresh at most hourly; rosters are cached for 24 hours. Missing players are not assumed to have zero goals.")
    if st.button("🔎 Load rosters + this-season player statistics"):
        st.session_state["player_stats_match_loaded"] = (competition, selected_match["id"], SEASON_YEAR)
    if st.session_state.get("player_stats_match_loaded") == (competition, selected_match["id"], SEASON_YEAR):
        all_results = {COMPETITIONS[competition]: finished}
        scorer_by_comp = {}
        issues = []
        with st.spinner("Loading published scorer feeds and this-season club results…"):
            for code in LEAGUES:
                try:
                    rows, maybe_truncated = load_scorers(code, api_token, SEASON_YEAR)
                    scorer_by_comp[code] = rows
                    if maybe_truncated:
                        issues.append(f"{LEAGUES[code]} may be truncated at its top-scorer API limit.")
                except StatsUnavailable as exc:
                    issues.append(str(exc))
                if code not in all_results:
                    try:
                        other_finished, _ = load_matches(code, api_token, SEASON_YEAR)
                        all_results[code] = other_finished
                    except ValueError as exc:
                        issues.append(f"{LEAGUES[code]} result data unavailable for shares: {exc}")
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
                for code, rows in scorer_by_comp.items():
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
                        entry["Goals leagues"].append(LEAGUES[code])
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

st.subheader("🥅 Optional manual anytime-goalscorer estimate")
st.warning("Manual model only. Enter participation and scoring assumptions yourself; predictions are not validated.")
with st.expander("Enter a player and scoring assumptions", expanded=False):
    player = st.text_input("Player name (enter manually)", placeholder="Enter a player")
    side = st.radio("Team", [home_name, away_name], horizontal=True)
    share = st.slider("Assumed share of team goals", 0.0, 1.0, 0.25, 0.01)
    minutes = st.slider("Expected minutes if playing", 0, 120, 80, 5)
    start_prob = st.slider("Probability player participates (1.0 if confirmed)", 0.0, 1.0, 0.8, 0.05)
    st.caption("Before lineups: enter your estimated participation probability. After confirmation: set to 100% if playing; adjust minutes as appropriate.")
    if st.button("Calculate player chance"):
        if not player.strip():
            st.error("Enter a player name first.")
        else:
            team_goals = hxg if side == home_name else axg
            scorer_prob = anytime_scorer(team_goals, share, minutes, start_prob)
            st.metric(f"{player.strip()} — anytime scorer estimate", f"{scorer_prob:.1%}")
            st.caption("Conditional model using assumed goal-share, playing time and participation. Not a validated player forecast.")

if use_live and len(finished) >= 25:
    st.divider()
    st.subheader("🧪 Historical rolling backtest")
    st.caption("Each result is predicted using only PRIOR days in the current API-returned competition data. This is a small, within-season test and cannot validate cross-league adjustments.")
    if st.button("Run historical backtest"):
        backtest = rolling_backtest(finished)
        if backtest:
            df = pd.DataFrame(backtest)
            c1, c2 = st.columns(2)
            c1.metric("Matches tested", len(df))
            c2.metric("Mean Brier score (lower is better)", f"{df['brier'].mean():.3f}")
            st.metric("Mean log loss (lower is better)", f"{df['log_loss'].mean():.3f}")
            st.dataframe(df, hide_index=True, use_container_width=True)
            st.download_button("Download backtest CSV", df.to_csv(index=False).encode(), "backtest.csv", "text/csv")
            st.caption("These are diagnostic scores, not claims of predictive accuracy. More seasons and independent holdouts are needed.")
        else:
            st.info("Not enough prior matches with three games per team to run a leak-free backtest.")
else:
    st.caption("Historical backtest available when a competition has at least 25 completed API fixtures.")

report = pd.DataFrame([{"competition": competition, "home": home_name, "away": away_name,
                        "projected_home_goals": hxg, "projected_away_goals": axg, "home_win": exact["home_win"],
                        "draw": exact["draw"], "away_win": exact["away_win"], "over_2_5": pred["over_25"],
                        "both_score": pred["btts"], "simulations": n,
                        "data_source": "football-data.org" if use_live else "manual", "season": SEASON_NAME}])
st.download_button("Download prediction CSV", report.to_csv(index=False).encode(), "soccer_prediction.csv", "text/csv")
st.caption(f"Important: {SEASON_NAME} only. Poisson match model is experimental, not a betting edge. Player statistics are provider-reported official scorer-list goals/assists/penalties, not full per-player xG/minutes/shots. Automatic player chances use seasonal team-goal shares, not same-position presets; they are uncalibrated and do not account for confirmed lineups or injuries. Champions League strengths are not cross-league calibrated. More simulations reduce sampling noise, not model error. Refresh happens on app activity.")
