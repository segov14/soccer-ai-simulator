"""Soccer Simulation Lab v2 — auto-loaded fixtures and results."""
from datetime import datetime, timezone
import os

import pandas as pd
import requests
import streamlit as st

from model import expected_goals, simulate, rating_from_results

st.set_page_config(page_title="Soccer AI Simulator", page_icon="⚽", layout="wide")
COMPETITIONS = {"La Liga": "PD", "Champions League": "CL", "Premier League": "PL"}
API_ROOT = "https://api.football-data.org/v4"


def get_token():
    """Cloud secret first; environment variable as local alternative."""
    try:
        secret = st.secrets.get("FOOTBALL_DATA_API_KEY", "")
    except (FileNotFoundError, KeyError):
        secret = ""
    return str(secret or os.getenv("FOOTBALL_DATA_API_KEY", "")).strip()


@st.cache_data(ttl=1800, show_spinner=False)
def load_matches(competition_code: str, api_token: str):
    """Request competition fixtures/results once per 30-minute cache period."""
    try:
        response = requests.get(
            f"{API_ROOT}/competitions/{competition_code}/matches",
            headers={"X-Auth-Token": api_token}, timeout=20,
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
    return finished, sorted(upcoming, key=lambda item: item["date_utc"])


def readable_time(utc_string):
    try:
        return datetime.fromisoformat(utc_string.replace("Z", "+00:00")).astimezone().strftime("%b %d, %Y · %I:%M %p %Z")
    except (ValueError, AttributeError):
        return utc_string or "Date not announced"


st.title("⚽ Soccer AI Simulator")
st.caption("La Liga · Champions League · Premier League | Automatically updated match data • Experimental probabilities")

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
            finished, upcoming = load_matches(COMPETITIONS[competition], api_token)
        # Build ratings using the same team IDs, not potentially inconsistent names.
        rating_matches = [{"home": str(m["hid"]), "away": str(m["aid"]), "hg": m["hg"], "ag": m["ag"]} for m in finished]
        ratings, base_goals = rating_from_results(rating_matches)
        st.success(f"Auto-data connected · {len(finished)} completed matches · {len(upcoming)} upcoming matches · refreshed approximately every 30 minutes")
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
a, b, c = st.columns(3)
a.metric(f"{home_name} win", f"{pred['home_win']:.1%}")
b.metric("Draw", f"{pred['draw']:.1%}")
c.metric(f"{away_name} win", f"{pred['away_win']:.1%}")
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

report = pd.DataFrame([{"competition": competition, "home": home_name, "away": away_name,
                        "projected_home_goals": hxg, "projected_away_goals": axg, "home_win": pred["home_win"],
                        "draw": pred["draw"], "away_win": pred["away_win"], "over_2_5": pred["over_25"],
                        "both_score": pred["btts"], "simulations": n,
                        "data_source": "football-data.org" if use_live else "manual"}])
st.download_button("Download prediction CSV", report.to_csv(index=False).encode(), "soccer_prediction.csv", "text/csv")
st.caption("Important: This is a simple Poisson simulation, NOT a machine-learning AI or a proven betting edge. No injuries, starting lineups, real xG, odds, or historical backtesting. More simulations reduce Monte Carlo noise, not model error. The API may limit competitions, future schedules and available results. Data refresh occurs on app activity, not continuously when nobody visits.")
