"""Transparent, reproducible football Monte Carlo model (not a betting guarantee)."""
import math
import numpy as np


def expected_goals(home_attack: float, home_defense: float, away_attack: float,
                   away_defense: float, base_goals: float = 1.35,
                   home_advantage: float = 1.12, neutral: bool = False):
    """Attack/defense multipliers: >1 defense means more goals conceded."""
    venue = 1.0 if neutral else home_advantage
    return (float(np.clip(base_goals * home_attack * away_defense * venue, 0.05, 5.5)),
            float(np.clip(base_goals * away_attack * home_defense / venue, 0.05, 5.5)))


def simulate(home_xg: float, away_xg: float, n: int = 10000, seed: int = 42):
    n = int(np.clip(n, 100, 100000))
    rng = np.random.default_rng(seed)
    h = rng.poisson(home_xg, n)
    a = rng.poisson(away_xg, n)
    counts = {}
    for hs, ag in zip(h, a):
        key = f"{hs}-{ag}"
        counts[key] = counts.get(key, 0) + 1
    scores = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:8]
    return {
        "n": n,
        "home_win": float(np.mean(h > a)),
        "draw": float(np.mean(h == a)),
        "away_win": float(np.mean(h < a)),
        "over_25": float(np.mean(h + a >= 3)),
        "under_25": float(np.mean(h + a <= 2)),
        "btts": float(np.mean((h > 0) & (a > 0))),
        "home_xg": home_xg,
        "away_xg": away_xg,
        "scores": [(s, count / n) for s, count in scores],
    }


def rating_from_results(matches, min_games=3):
    """Simple empirical goals-based ratings, shrunk toward league average.

    matches: iterable of dicts with home, away, hg, ag. Each completed match
    is one observation. Statistics use all games rather than separate venues.
    """
    games = list(matches)
    if not games:
        return {}, 1.35
    avg = max(0.4, sum(m['hg'] + m['ag'] for m in games) / (2 * len(games)))
    teams = {}
    for m in games:
        for team, gf, ga in ((m['home'], m['hg'], m['ag']), (m['away'], m['ag'], m['hg'])):
            s = teams.setdefault(team, {'gf': 0, 'ga': 0, 'games': 0})
            s['gf'] += gf
            s['ga'] += ga
            s['games'] += 1
    shrink = 8.0
    return {name: {
        'attack': float(np.clip((x['gf'] + shrink * avg) / ((x['games'] + shrink) * avg), 0.5, 1.8)),
        'defense': float(np.clip((x['ga'] + shrink * avg) / ((x['games'] + shrink) * avg), 0.5, 1.8)),
        'games': x['games'],
    } for name, x in teams.items() if x['games'] >= min_games}, avg
