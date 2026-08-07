"""Options Greeks alignment scanner for directional call/put setups.

Scans option chains and ranks contracts where delta, gamma, theta and vega are
simultaneously aligned for a long call or long put thesis. Greeks come from the
broker when the source publishes them (IBKR) and are otherwise computed from
implied volatility with Black-Scholes (Yahoo). Output is a markdown report
suitable for manually placing the trade in thinkorswim.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from typing import Iterable, Optional

from chain_providers import (
    IBKR_DEFAULT_CLIENT_ID,
    IBKR_DEFAULT_HOST,
    IBKR_DEFAULT_PORT,
    ChainProvider,
    ContractQuote,
    Side,
    as_float as _as_float,
    build_provider,
)

TRADING_DAYS = 252.0
CALENDAR_DAYS = 365.0


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


@dataclass(frozen=True)
class Greeks:
    delta: float
    gamma: float
    theta: float
    vega: float


def black_scholes_greeks(
    side: Side,
    spot: float,
    strike: float,
    years_to_expiry: float,
    iv: float,
    rate: float,
    dividend_yield: float,
) -> Greeks:
    """Greeks for one contract. theta is per calendar day, vega per 1 vol point."""
    t = max(years_to_expiry, 1.0 / (CALENDAR_DAYS * 24.0))
    sigma = max(iv, 1e-4)
    sqrt_t = math.sqrt(t)
    d1 = (math.log(spot / strike) + (rate - dividend_yield + 0.5 * sigma**2) * t) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    disc_q = math.exp(-dividend_yield * t)
    disc_r = math.exp(-rate * t)

    gamma = disc_q * _norm_pdf(d1) / (spot * sigma * sqrt_t)
    vega = spot * disc_q * _norm_pdf(d1) * sqrt_t / 100.0
    common_theta = -spot * disc_q * _norm_pdf(d1) * sigma / (2.0 * sqrt_t)

    if side == "call":
        delta = disc_q * _norm_cdf(d1)
        theta = common_theta - rate * strike * disc_r * _norm_cdf(d2) + dividend_yield * spot * disc_q * _norm_cdf(d1)
    else:
        delta = -disc_q * _norm_cdf(-d1)
        theta = common_theta + rate * strike * disc_r * _norm_cdf(-d2) - dividend_yield * spot * disc_q * _norm_cdf(-d1)

    return Greeks(delta=delta, gamma=gamma, theta=theta / CALENDAR_DAYS, vega=vega)


@dataclass(frozen=True)
class AlignmentThresholds:
    """Bands every greek must satisfy for a setup to count as aligned."""

    min_abs_delta: float = 0.35
    max_abs_delta: float = 0.65
    # Gamma gain over an expected one-day move divided by one day of decay.
    # A fairly priced option sits at 1.0; below that, decay outruns convexity.
    min_gamma_theta_ratio: float = 0.85
    # Daily decay as a fraction of the premium paid.
    max_theta_burn: float = 0.035
    # Vega exposure per dollar of premium; too high means the trade is an IV bet.
    max_vega_ratio: float = 0.30
    max_iv: float = 1.20


@dataclass(frozen=True)
class LiquidityFilters:
    min_open_interest: int = 250
    min_volume: int = 10
    max_spread_pct: float = 0.12
    min_premium: float = 0.20


@dataclass
class Setup:
    ticker: str
    side: Side
    contract_symbol: str
    tos_symbol: str
    expiration: str
    dte: int
    spot: float
    strike: float
    mid: float
    bid: float
    ask: float
    spread_pct: float
    open_interest: int
    volume: int
    iv: float
    delta: float
    gamma: float
    theta: float
    vega: float
    gamma_theta_ratio: float
    theta_burn: float
    vega_ratio: float
    score: float
    aligned: bool
    notes: list[str]


def _tos_symbol(ticker: str, expiration: str, side: Side, strike: float) -> str:
    exp = datetime.strptime(expiration, "%Y-%m-%d").strftime("%y%m%d")
    strike_txt = f"{strike:g}"
    return f".{ticker}{exp}{'C' if side == 'call' else 'P'}{strike_txt}"


def _score(setup_metrics: dict[str, float], thresholds: AlignmentThresholds) -> float:
    """0-100 score. Rewards balanced delta, convexity per unit decay and cheap vega."""
    abs_delta = setup_metrics["abs_delta"]
    center = (thresholds.min_abs_delta + thresholds.max_abs_delta) / 2.0
    half_width = (thresholds.max_abs_delta - thresholds.min_abs_delta) / 2.0
    delta_score = max(0.0, 1.0 - abs(abs_delta - center) / half_width)

    gamma_score = min(1.0, setup_metrics["gamma_theta_ratio"] / thresholds.min_gamma_theta_ratio)
    theta_score = max(0.0, 1.0 - setup_metrics["theta_burn"] / thresholds.max_theta_burn)
    vega_score = max(0.0, 1.0 - setup_metrics["vega_ratio"] / thresholds.max_vega_ratio)

    return round(100.0 * (0.30 * delta_score + 0.30 * gamma_score + 0.25 * theta_score + 0.15 * vega_score), 1)


def _evaluate_chain(
    ticker: str,
    quotes: Iterable[ContractQuote],
    spot: float,
    expiration: str,
    dte: int,
    rate: float,
    dividend_yield: float,
    thresholds: AlignmentThresholds,
    liquidity: LiquidityFilters,
) -> list[Setup]:
    setups: list[Setup] = []
    years = max(dte, 0) / CALENDAR_DAYS

    for quote in quotes:
        bid, ask = quote.bid, quote.ask
        if bid <= 0.0 or ask <= 0.0:
            continue
        mid = (bid + ask) / 2.0
        spread_pct = (ask - bid) / mid
        side, strike, iv = quote.side, quote.strike, quote.iv

        if mid < liquidity.min_premium or spread_pct > liquidity.max_spread_pct:
            continue
        if quote.open_interest < liquidity.min_open_interest or quote.volume < liquidity.min_volume:
            continue
        if iv <= 0.0 or iv > thresholds.max_iv:
            continue

        greeks = quote.greeks or black_scholes_greeks(side, spot, strike, years, iv, rate, dividend_yield)
        theta_per_day = abs(greeks.theta)
        if theta_per_day < 1e-4:
            continue

        # Convexity earned over a one-standard-deviation daily move: 0.5 * gamma * move^2.
        expected_move = spot * iv / math.sqrt(CALENDAR_DAYS)
        gamma_gain = 0.5 * greeks.gamma * expected_move**2
        metrics = {
            "abs_delta": abs(greeks.delta),
            "gamma_theta_ratio": gamma_gain / theta_per_day,
            "theta_burn": theta_per_day / mid,
            "vega_ratio": greeks.vega / mid,
        }

        notes: list[str] = []
        if not thresholds.min_abs_delta <= metrics["abs_delta"] <= thresholds.max_abs_delta:
            notes.append(f"delta {metrics['abs_delta']:.2f} outside {thresholds.min_abs_delta}-{thresholds.max_abs_delta}")
        if metrics["gamma_theta_ratio"] < thresholds.min_gamma_theta_ratio:
            notes.append(f"gamma/theta {metrics['gamma_theta_ratio']:.2f} below {thresholds.min_gamma_theta_ratio}")
        if metrics["theta_burn"] > thresholds.max_theta_burn:
            notes.append(f"theta burn {metrics['theta_burn']:.1%}/day above {thresholds.max_theta_burn:.1%}")
        if metrics["vega_ratio"] > thresholds.max_vega_ratio:
            notes.append(f"vega/premium {metrics['vega_ratio']:.2f} above {thresholds.max_vega_ratio}")

        setups.append(
            Setup(
                ticker=ticker,
                side=side,
                contract_symbol=quote.contract_symbol,
                tos_symbol=_tos_symbol(ticker, expiration, side, strike),
                expiration=expiration,
                dte=dte,
                spot=round(spot, 2),
                strike=strike,
                mid=round(mid, 2),
                bid=bid,
                ask=ask,
                spread_pct=round(spread_pct, 4),
                open_interest=quote.open_interest,
                volume=quote.volume,
                iv=round(iv, 4),
                delta=round(greeks.delta, 4),
                gamma=round(greeks.gamma, 5),
                theta=round(greeks.theta, 4),
                vega=round(greeks.vega, 4),
                gamma_theta_ratio=round(metrics["gamma_theta_ratio"], 3),
                theta_burn=round(metrics["theta_burn"], 4),
                vega_ratio=round(metrics["vega_ratio"], 3),
                score=_score(metrics, thresholds),
                aligned=not notes,
                notes=notes,
            )
        )

    return setups


def scan_ticker(
    provider: ChainProvider,
    ticker: str,
    min_dte: int,
    max_dte: int,
    rate: float,
    thresholds: AlignmentThresholds,
    liquidity: LiquidityFilters,
    today: Optional[date] = None,
) -> list[Setup]:
    today = today or datetime.now(timezone.utc).date()
    spot = provider.spot(ticker)
    if spot is None:
        return []

    dividend_yield = provider.dividend_yield(ticker)

    setups: list[Setup] = []
    for expiration in provider.expirations(ticker):
        dte = (datetime.strptime(expiration, "%Y-%m-%d").date() - today).days
        if not min_dte <= dte <= max_dte:
            continue
        setups.extend(
            _evaluate_chain(
                ticker,
                provider.quotes(ticker, expiration),
                spot,
                expiration,
                dte,
                rate,
                dividend_yield,
                thresholds,
                liquidity,
            )
        )
    return setups


def render_markdown(setups: Iterable[Setup], top_n: int, aligned_only: bool, source: str = "yahoo") -> str:
    ranked = sorted(setups, key=lambda s: (s.aligned, s.score), reverse=True)
    if aligned_only:
        ranked = [s for s in ranked if s.aligned]
    ranked = ranked[:top_n]

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# Greeks alignment scan — {stamp} (source: {source})", ""]
    if not ranked:
        lines.append("No contracts passed the liquidity filters and greek alignment bands.")
        return "\n".join(lines)

    lines += [
        "| # | Ticker | Side | Contract (ToS) | Exp | DTE | Spot | Strike | Mid | IV | Delta | Gamma | Theta/day | Vega | Gamma/Theta | Theta burn | Score | Aligned |",
        "|---|--------|------|----------------|-----|-----|------|--------|-----|----|-------|-------|-----------|------|-------------|------------|-------|---------|",
    ]
    for i, s in enumerate(ranked, start=1):
        lines.append(
            f"| {i} | {s.ticker} | {s.side.upper()} | `{s.tos_symbol}` | {s.expiration} | {s.dte} | {s.spot} | "
            f"{s.strike:g} | {s.mid} | {s.iv:.1%} | {s.delta:+.2f} | {s.gamma:.4f} | {s.theta:+.3f} | {s.vega:.3f} | "
            f"{s.gamma_theta_ratio:.2f} | {s.theta_burn:.2%} | {s.score} | {'yes' if s.aligned else 'no'} |"
        )

    misaligned = [s for s in ranked if not s.aligned]
    if misaligned:
        lines += ["", "## Why the near-misses failed", ""]
        for s in misaligned:
            lines.append(f"- `{s.tos_symbol}`: " + "; ".join(s.notes))

    source_note = (
        "Greeks are IBKR model greeks taken straight from the live chain."
        if source == "ibkr"
        else "Quotes are delayed roughly 15 minutes and greeks are computed locally from implied volatility."
    )
    lines += [
        "",
        f"_{source_note}_",
        "",
        "## Reading the columns",
        "",
        "- **Gamma/Theta**: convexity earned on a one-sigma daily move divided by one day of decay. A fairly priced option sits near 1.0.",
        "- **Theta burn**: daily decay as a percentage of the premium paid.",
        "- **Vega**: dollars gained per 1 volatility point; a high vega/premium ratio turns the trade into an IV bet.",
        "",
        "Not investment advice; verify the quote and greeks in thinkorswim before placing an order.",
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tickers", nargs="+", help="Underlying symbols, e.g. SPY QQQ AAPL")
    parser.add_argument(
        "--source",
        choices=["yahoo", "ibkr"],
        default="yahoo",
        help="yahoo: free, ~15 min delayed, greeks computed locally. "
        "ibkr: live quotes and IBKR model greeks, needs a running TWS/IB Gateway.",
    )
    parser.add_argument("--ibkr-host", default=IBKR_DEFAULT_HOST)
    parser.add_argument(
        "--ibkr-port",
        type=int,
        default=IBKR_DEFAULT_PORT,
        help="7497 TWS paper, 7496 TWS live, 4002 Gateway paper, 4001 Gateway live",
    )
    parser.add_argument("--ibkr-client-id", type=int, default=IBKR_DEFAULT_CLIENT_ID)
    parser.add_argument("--min-dte", type=int, default=7)
    parser.add_argument("--max-dte", type=int, default=45)
    parser.add_argument("--rate", type=float, default=0.04, help="Risk-free rate as a decimal")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--side", choices=["call", "put", "both"], default="both")
    parser.add_argument("--aligned-only", action="store_true", help="Drop contracts that miss any greek band")
    parser.add_argument("--min-abs-delta", type=float, default=AlignmentThresholds.min_abs_delta)
    parser.add_argument("--max-abs-delta", type=float, default=AlignmentThresholds.max_abs_delta)
    parser.add_argument("--min-gamma-theta", type=float, default=AlignmentThresholds.min_gamma_theta_ratio)
    parser.add_argument("--max-theta-burn", type=float, default=AlignmentThresholds.max_theta_burn)
    parser.add_argument("--max-vega-ratio", type=float, default=AlignmentThresholds.max_vega_ratio)
    parser.add_argument("--min-open-interest", type=int, default=LiquidityFilters.min_open_interest)
    parser.add_argument("--min-volume", type=int, default=LiquidityFilters.min_volume)
    parser.add_argument("--max-spread-pct", type=float, default=LiquidityFilters.max_spread_pct)
    parser.add_argument("--json-out", help="Also write the raw ranked setups to this JSON path")
    parser.add_argument("--markdown-out", help="Write the markdown report to this path instead of stdout only")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    thresholds = AlignmentThresholds(
        min_abs_delta=args.min_abs_delta,
        max_abs_delta=args.max_abs_delta,
        min_gamma_theta_ratio=args.min_gamma_theta,
        max_theta_burn=args.max_theta_burn,
        max_vega_ratio=args.max_vega_ratio,
    )
    liquidity = LiquidityFilters(
        min_open_interest=args.min_open_interest,
        min_volume=args.min_volume,
        max_spread_pct=args.max_spread_pct,
    )

    if args.source == "ibkr":
        try:
            provider = build_provider(
                "ibkr", host=args.ibkr_host, port=args.ibkr_port, client_id=args.ibkr_client_id
            )
        except (OSError, ImportError) as exc:
            print(
                f"error: cannot reach IBKR at {args.ibkr_host}:{args.ibkr_port} ({exc}). "
                "Start TWS or IB Gateway, log in, and enable API socket clients.",
                file=sys.stderr,
            )
            return 2
    else:
        provider = build_provider("yahoo")

    all_setups: list[Setup] = []
    try:
        for ticker in args.tickers:
            try:
                all_setups.extend(
                    scan_ticker(
                        provider, ticker.upper(), args.min_dte, args.max_dte, args.rate, thresholds, liquidity
                    )
                )
            except Exception as exc:  # a single bad symbol must not kill the scan
                print(f"warning: {ticker}: {exc}", file=sys.stderr)
    finally:
        close = getattr(provider, "close", None)
        if callable(close):
            close()

    if args.side != "both":
        all_setups = [s for s in all_setups if s.side == args.side]

    report = render_markdown(all_setups, args.top, args.aligned_only, source=args.source)
    print(report)

    if args.markdown_out:
        with open(args.markdown_out, "w") as handle:
            handle.write(report + "\n")
    if args.json_out:
        ranked = sorted(all_setups, key=lambda s: (s.aligned, s.score), reverse=True)
        with open(args.json_out, "w") as handle:
            json.dump([asdict(s) for s in ranked], handle, indent=2)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
