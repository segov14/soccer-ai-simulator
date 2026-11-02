from pathlib import Path

from model import simulate


def test_simulation_count_fixed_to_100000():
    source = (Path(__file__).parent / "app.py").read_text(encoding="utf-8")
    assert "n = 100000" in source
    assert "n = 25000" not in source
    assert "25,000 score simulations" not in source


def test_engine_handles_100000_simulations():
    result = simulate(1.88, 2.30, n=100000, seed=42)
    assert abs(result["home_win"] + result["draw"] + result["away_win"] - 1) < 1e-10
    assert result == simulate(1.88, 2.30, n=100000, seed=42)
