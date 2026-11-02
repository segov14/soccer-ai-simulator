"""Season-only football-data.org scorer stats, with strict data provenance.

This feed is a *top-scorers list*, not comprehensive player game logs. A missing
player entry is missing information, NEVER zero goals. The free API does not
supply playing time, shots, shots-on-target or current starting XIs here.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import math
import re
import unicodedata
from urllib.parse import quote

import requests

ROOT = "https://api.football-data.org/v4"
LEAGUES = {"PD": "La Liga", "CL": "Champions League", "PL": "Premier League"}

class StatsUnavailable(Exception):
    """Unavailable, restricted, outdated or invalid official scorer data."""


def current_season_year(today=None):
    today = today or datetime.now(timezone.utc).date()
    return today.year if today.month >= 7 else today.year - 1


def season_label(year):
    return f"{int(year)}–{(int(year) + 1) % 100:02d}"


def valid_season(payload, year):
    """Ensure the provider didn't silently return a different season."""
    start = (payload.get("season") or {}).get("startDate")
    filtered = (payload.get("filters") or {}).get("season")
    if start and str(start)[:4].isdigit():
        return int(str(start)[:4]) == int(year)
    return filtered is not None and str(filtered) == str(year)


def _integer_or_none(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    return None


def parse_scorers(payload, code, year):
    if not isinstance(payload, dict) or not valid_season(payload, year):
        raise StatsUnavailable(f"{code} scorer feed did not confirm the {season_label(year)} season.")
    if not isinstance(payload.get("scorers"), list):
        raise StatsUnavailable(f"{code} scorer feed lacks a scorer list.")
    rows = []
    for item in payload["scorers"]:
        p, t = item.get("player") or {}, item.get("team") or {}
        goals = _integer_or_none(item.get("goals"))
        if goals is None or not p.get("name") or t.get("id") is None:
            continue
        rows.append({"id": p.get("id"), "name": p["name"], "team_id": int(t["id"]),
                     "team": t.get("name") or "Unknown", "code": code, "goals": goals,
                     "assists": _integer_or_none(item.get("assists")),
                     "penalties": _integer_or_none(item.get("penalties")),
                     "played_matches": _integer_or_none(item.get("playedMatches")),
                     "season": int(year),
                     "source_url": f"{ROOT}/competitions/{quote(code)}/scorers?season={int(year)}"})
    filters = payload.get("filters") or {}
    requested_limit = _integer_or_none(filters.get("limit"))
    # If count equals limit, completeness of the published leaderboard is unknown.
    truncated_possible = bool(requested_limit and len(payload["scorers"]) >= requested_limit)
    return rows, truncated_possible


def fetch_scorers(code, token, year, requested_limit=200, requester=None):
    """Return (rows, may_be_truncated) from official API; never fall back to older year."""
    if code not in LEAGUES:
        raise StatsUnavailable("Unsupported competition.")
    if not token:
        raise StatsUnavailable("Missing football-data.org key.")
    requester = requester or requests.get
    url = f"{ROOT}/competitions/{code}/scorers"
    for limit in (requested_limit, 100, 50):
        try:
            response = requester(url, headers={"X-Auth-Token": token},
                                 params={"season": int(year), "limit": limit}, timeout=20)
            if response.status_code == 400 and limit != 50:
                continue  # some provider plans cap the leaderboard size
            if response.status_code in (401, 403, 404):
                raise StatsUnavailable(f"{code}: scorer data not included in this API subscription.")
            if response.status_code == 429:
                raise StatsUnavailable("Provider's request limit reached; try later.")
            response.raise_for_status()
            return parse_scorers(response.json(), code, year)
        except StatsUnavailable:
            raise
        except (requests.RequestException, ValueError, TypeError) as exc:
            raise StatsUnavailable(f"{code}: couldn't load current-season scorer stats.") from exc
    raise StatsUnavailable(f"{code}: scorer endpoint rejected the requested limit.")


def season_matches_only(finished, upcoming, year):
    """Retain matches whose kickoff dates lie within the requested season window.

    The callers must supply match results explicitly requested with season=year.
    """
    start = f"{year}-07-01"
    end = f"{year + 1}-07-01"
    def keep(m):
        dt = str(m.get("date_utc") or "")[:10]
        return len(dt) == 10 and start <= dt < end
    return [m for m in finished if keep(m)], [m for m in upcoming if keep(m)]


def team_totals_by_comp(results_by_code):
    """Only finished matches from explicitly queried current season."""
    totals = defaultdict(lambda: {"games": 0, "goals": 0})
    for code, matches in results_by_code.items():
        if code not in LEAGUES:
            continue
        for m in matches:
            for team_id, goals in ((m.get("hid"), m.get("hg")),
                                   (m.get("aid"), m.get("ag"))):
                if team_id is None or not isinstance(goals, int) or goals < 0:
                    continue
                k = (int(team_id), code)
                totals[k]["games"] += 1
                totals[k]["goals"] += goals
    return dict(totals)


def _norm_name(text):
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    plain = "".join(c for c in normalized if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", plain.casefold())


def combine_player_rows(roster, team_id, scorer_by_comp, team_totals, forecast_team_goals):
    """All roster members remain. Join by provider player ID, else unique full name.

    Probability is NOT a calibrated forecast: extrapolates the player's current
    season reported share of team goals to the team's fixture-level goal mean.
    No assumptions about minutes, likely starters or missing scoring entries.
    """
    if not math.isfinite(float(forecast_team_goals)) or forecast_team_goals < 0:
        raise ValueError("Invalid team goal projection")
    available = []
    for code, rows in scorer_by_comp.items():
        for row in rows:
            if code in LEAGUES and row.get("team_id") == int(team_id):
                available.append(row)
    by_id = defaultdict(list)
    by_name = defaultdict(list)
    for row in available:
        if row.get("id") is not None:
            by_id[str(row["id"])].append(row)
        by_name[_norm_name(row["name"])].append(row)

    result = []
    for p in roster:
        uid = p.get("ID")
        matched = by_id.get(str(uid), []) if uid is not None else []
        if not matched and uid is None:
            candidates = by_name.get(_norm_name(p.get("Name")), [])
            # only if exact normalized full name corresponds to ONE provider player ID
            unique_ids = {r.get("id") or (r["name"], r["team_id"]) for r in candidates}
            matched = candidates if len(unique_ids) == 1 else []
        # Deduplicate duplicate scorer rows from same competition
        unique = {r["code"]: r for r in matched}
        entries = list(unique.values())
        codes = sorted(unique)
        goals = sum(int(x["goals"]) for x in entries)
        assists = sum(int(x["assists"]) for x in entries) if entries and all(x["assists"] is not None for x in entries) else None
        penalties = sum(int(x["penalties"]) for x in entries) if entries and all(x["penalties"] is not None for x in entries) else None
        team_goals = sum(team_totals.get((int(team_id), code), {}).get("goals", 0) for code in codes)
        games = sum(team_totals.get((int(team_id), code), {}).get("games", 0) for code in codes)
        # A team goal share can be estimated only if numerator and denominator
        # describe the exact same competitions and scorer goals do not exceed team goals.
        complete = all(team_totals.get((int(team_id), code), {}).get("games", 0) > 0 for code in codes)
        can_estimate = bool(entries and complete and games >= 3 and team_goals >= goals and team_goals > 0)
        goal_share = goals / team_goals if can_estimate else None
        anytime = 1 - math.exp(-float(forecast_team_goals) * goal_share) if can_estimate else None
        result.append({"Player": p.get("Name", ""), "Position": p.get("Position", "Unknown"),
                       "Goals": goals if entries else None,
                       "Assists": assists,
                       "Penalties": penalties,
                       "Goal involvements": goals + assists if entries and assists is not None else None,
                       "Team matches": games if entries and complete else None,
                       "Team goals": team_goals if entries and complete else None,
                       "Goals / team match": round(goals / games, 3) if entries and complete and games else None,
                       "Share of team goals": round(goal_share, 4) if goal_share is not None else None,
                       "Anytime chance (experimental)": anytime,
                       "Competitions reported": ", ".join(LEAGUES[c] for c in codes) if codes else "Not in scorer feed",
                       "Data status": (f"{season_label(entries[0]['season'])} scorer data" if can_estimate else
                                       "Some verified stats; not enough team results" if entries else
                                       "No published player stats — not zero goals"),
                       "Source URLs": [x["source_url"] for x in entries],
                       "Season": entries[0]["season"] if entries else None})
    return sorted(result, key=lambda r: (r["Anytime chance (experimental)"] is None,
                                       -(r["Anytime chance (experimental)"] or 0), r["Player"]))
