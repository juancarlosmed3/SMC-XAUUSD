import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from greeks_alignment_scanner import (  # noqa: E402  (path set up above)
    AlignmentThresholds,
    _as_float,
    _score,
    _tos_symbol,
    black_scholes_greeks,
    render_markdown,
)

SPOT = 100.0
STRIKE = 100.0
YEARS = 30 / 365
IV = 0.25
RATE = 0.04


def test_atm_call_and_put_deltas_satisfy_parity():
    call = black_scholes_greeks("call", SPOT, STRIKE, YEARS, IV, RATE, 0.0)
    put = black_scholes_greeks("put", SPOT, STRIKE, YEARS, IV, RATE, 0.0)
    assert math.isclose(call.delta - put.delta, 1.0, abs_tol=1e-9)
    assert math.isclose(call.gamma, put.gamma, rel_tol=1e-12)
    assert math.isclose(call.vega, put.vega, rel_tol=1e-12)
    assert 0.45 < call.delta < 0.60
    assert -0.60 < put.delta < -0.40


def test_long_options_decay():
    for side in ("call", "put"):
        assert black_scholes_greeks(side, SPOT, STRIKE, YEARS, IV, RATE, 0.0).theta < 0


def test_gamma_and_vega_peak_at_the_money():
    atm = black_scholes_greeks("call", SPOT, 100.0, YEARS, IV, RATE, 0.0)
    otm = black_scholes_greeks("call", SPOT, 130.0, YEARS, IV, RATE, 0.0)
    assert atm.gamma > otm.gamma
    assert atm.vega > otm.vega


def test_gamma_gain_matches_decay_for_a_zero_carry_option():
    """0.5 * gamma * (one-sigma daily move)^2 equals one calendar day of theta."""
    greeks = black_scholes_greeks("call", SPOT, STRIKE, YEARS, IV, 0.0, 0.0)
    move = SPOT * IV / math.sqrt(365.0)
    assert math.isclose(0.5 * greeks.gamma * move**2 / abs(greeks.theta), 1.0, rel_tol=1e-6)


def test_as_float_handles_nan_and_none():
    assert _as_float(float("nan")) == 0.0
    assert _as_float(None) == 0.0
    assert _as_float("3.5") == 3.5
    assert _as_float(None, default=1.0) == 1.0


def test_score_is_highest_for_a_centered_balanced_setup():
    thresholds = AlignmentThresholds()
    best = _score(
        {"abs_delta": 0.50, "gamma_theta_ratio": 1.5, "theta_burn": 0.0, "vega_ratio": 0.0},
        thresholds,
    )
    worst = _score(
        {"abs_delta": 0.90, "gamma_theta_ratio": 0.1, "theta_burn": 0.05, "vega_ratio": 0.5},
        thresholds,
    )
    assert best == 100.0
    assert worst < 10.0


def test_tos_symbol_format():
    assert _tos_symbol("SPY", "2026-09-18", "call", 777.0) == ".SPY260918C777"
    assert _tos_symbol("AAPL", "2026-09-18", "put", 315.5) == ".AAPL260918P315.5"


def test_render_markdown_without_results():
    assert "No contracts passed" in render_markdown([], top_n=5, aligned_only=True)
