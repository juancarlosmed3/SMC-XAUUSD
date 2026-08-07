import math
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chain_providers import BrokerGreeks, ContractQuote  # noqa: E402  (path set up above)
from greeks_alignment_scanner import (  # noqa: E402
    AlignmentThresholds,
    LiquidityFilters,
    _as_float,
    _evaluate_chain,
    _score,
    _tos_symbol,
    black_scholes_greeks,
    build_parser,
    rank_setups,
    render_markdown,
    reported_setups,
    scan_ticker,
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


def test_zero_thresholds_disable_a_band_instead_of_dividing_by_zero():
    metrics = {"abs_delta": 0.9, "gamma_theta_ratio": 0.1, "theta_burn": 0.5, "vega_ratio": 2.0}
    disabled = AlignmentThresholds(
        min_abs_delta=0.5,
        max_abs_delta=0.5,
        min_gamma_theta_ratio=0.0,
        max_theta_burn=0.0,
        max_vega_ratio=0.0,
    )
    assert _score(metrics, disabled) == 100.0


def test_top_must_be_at_least_one():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["SPY", "--top", "-1"])
    with pytest.raises(SystemExit):
        build_parser().parse_args(["SPY", "--top", "0"])


def test_reported_setups_applies_aligned_only_and_top():
    setups = scan_ticker(
        _FakeProvider(),
        "FAKE",
        min_dte=7,
        max_dte=45,
        rate=0.0,
        thresholds=AlignmentThresholds(),
        liquidity=LiquidityFilters(),
        today=date(2026, 2, 1),
    )
    assert len(rank_setups(setups)) == 2
    assert len(reported_setups(setups, top_n=1, aligned_only=True)) == 1


def test_tos_symbol_format():
    assert _tos_symbol("SPY", "2026-09-18", "call", 777.0) == ".SPY260918C777"
    assert _tos_symbol("AAPL", "2026-09-18", "put", 315.5) == ".AAPL260918P315.5"


def test_render_markdown_without_results():
    assert "No contracts passed" in render_markdown([], top_n=5, aligned_only=True)


class _FakeProvider:
    """Two ATM contracts and one illiquid one, without touching the network."""

    name = "fake"

    def spot(self, ticker):
        return 100.0

    def dividend_yield(self, ticker):
        return 0.0

    def expirations(self, ticker):
        return ["2026-03-02", "2027-01-15"]

    def quotes(self, ticker, expiration):
        return [
            ContractQuote("call", 100.0, 4.9, 5.1, 5000, 400, 0.25, "FAKE260302C100"),
            ContractQuote("put", 100.0, 4.7, 4.9, 4000, 300, 0.25, "FAKE260302P100"),
            ContractQuote("call", 150.0, 0.05, 0.30, 3, 0, 0.60, "FAKE260302C150"),
        ]


def test_scan_ticker_filters_by_dte_and_liquidity():
    setups = scan_ticker(
        _FakeProvider(),
        "FAKE",
        min_dte=7,
        max_dte=45,
        rate=0.0,
        thresholds=AlignmentThresholds(),
        liquidity=LiquidityFilters(),
        today=date(2026, 2, 1),
    )
    # Only the 2026-03-02 expiry is inside the DTE window, and the wide-spread
    # 150 strike is dropped before greeks are computed.
    assert {(s.side, s.strike) for s in setups} == {("call", 100.0), ("put", 100.0)}
    assert all(s.dte == 29 for s in setups)
    assert all(s.aligned for s in setups)


def test_broker_greeks_are_used_verbatim_when_the_source_supplies_them():
    quote = ContractQuote(
        "call",
        100.0,
        4.9,
        5.1,
        5000,
        400,
        0.25,
        "FAKE260302C100",
        greeks=BrokerGreeks(delta=0.42, gamma=0.031, theta=-0.055, vega=0.111),
    )
    [setup] = _evaluate_chain(
        "FAKE",
        [quote],
        spot=100.0,
        expiration="2026-03-02",
        dte=29,
        rate=0.04,
        dividend_yield=0.02,
        thresholds=AlignmentThresholds(),
        liquidity=LiquidityFilters(),
    )
    assert (setup.delta, setup.gamma, setup.theta, setup.vega) == (0.42, 0.031, -0.055, 0.111)
