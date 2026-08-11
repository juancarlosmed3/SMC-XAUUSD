"""Option chain data providers.

Two sources are supported:

- ``yahoo`` (default): free and delayed roughly 15 minutes, no credentials.
  Only implied volatility is published, so greeks are computed locally.
- ``ibkr``: Interactive Brokers via a running TWS or IB Gateway. IBKR publishes
  its own model greeks, so they are used as-is instead of being recomputed.

Both providers return the same :class:`ContractQuote` rows so the scanner does
not care where the chain came from.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional, Protocol

Side = Literal["call", "put"]

IBKR_DEFAULT_HOST = "127.0.0.1"
# 7497 = TWS paper, 7496 = TWS live, 4002 = IB Gateway paper, 4001 = IB Gateway live.
IBKR_DEFAULT_PORT = 7497
IBKR_DEFAULT_CLIENT_ID = 17
# IBKR caps concurrent market data lines, so only strikes near spot are requested.
IBKR_STRIKE_WINDOW = 0.20


def as_float(value: object, default: float = 0.0) -> float:
    """Coerce a provider field to a float, treating NaN/None/garbage as missing."""
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return default if math.isnan(result) else result


@dataclass(frozen=True)
class BrokerGreeks:
    delta: float
    gamma: float
    theta: float
    vega: float


@dataclass(frozen=True)
class ContractQuote:
    side: Side
    strike: float
    bid: float
    ask: float
    open_interest: int
    volume: int
    iv: float
    contract_symbol: str
    # Populated only when the source publishes its own greeks (IBKR).
    greeks: Optional[BrokerGreeks] = None


class ChainProvider(Protocol):
    name: str

    def spot(self, ticker: str) -> Optional[float]: ...

    def dividend_yield(self, ticker: str) -> float: ...

    def expirations(self, ticker: str) -> list[str]: ...

    def quotes(self, ticker: str, expiration: str) -> list[ContractQuote]: ...


class YahooProvider:
    """Delayed chains from Yahoo Finance via yfinance. Greeks are computed locally."""

    name = "yahoo"

    def __init__(self) -> None:
        import yfinance as yf

        self._yf = yf
        self._tickers: dict[str, object] = {}

    def _ticker(self, ticker: str):
        if ticker not in self._tickers:
            self._tickers[ticker] = self._yf.Ticker(ticker)
        return self._tickers[ticker]

    def spot(self, ticker: str) -> Optional[float]:
        history = self._ticker(ticker).history(period="5d", interval="1d")
        if history.empty:
            return None
        return float(history["Close"].iloc[-1])

    def dividend_yield(self, ticker: str) -> float:
        """yfinance reports ``dividendYield`` in percent (0.44 means 0.44%) while
        ``trailingAnnualDividendYield`` is already a fraction, so prefer the latter."""
        try:
            info = self._ticker(ticker).info
        except Exception:
            return 0.0
        trailing = as_float(info.get("trailingAnnualDividendYield"))
        if trailing > 0.0:
            return trailing
        return as_float(info.get("dividendYield")) / 100.0

    def expirations(self, ticker: str) -> list[str]:
        return list(self._ticker(ticker).options)

    def quotes(self, ticker: str, expiration: str) -> list[ContractQuote]:
        chain = self._ticker(ticker).option_chain(expiration)
        rows: list[ContractQuote] = []
        for side, frame in (("call", chain.calls), ("put", chain.puts)):
            for row in frame.itertuples():
                rows.append(
                    ContractQuote(
                        side=side,
                        strike=as_float(row.strike),
                        bid=as_float(getattr(row, "bid", 0.0)),
                        ask=as_float(getattr(row, "ask", 0.0)),
                        open_interest=int(as_float(getattr(row, "openInterest", 0.0))),
                        volume=int(as_float(getattr(row, "volume", 0.0))),
                        iv=as_float(getattr(row, "impliedVolatility", 0.0)),
                        contract_symbol=str(row.contractSymbol),
                    )
                )
        return rows


class IBKRProvider:
    """Live chains and model greeks from a running TWS or IB Gateway.

    Requires `ib_async` and an authenticated gateway on ``host:port``. IBKR
    forces a re-login roughly daily, so unattended use needs IBC or equivalent.
    """

    name = "ibkr"

    def __init__(
        self,
        host: str = IBKR_DEFAULT_HOST,
        port: int = IBKR_DEFAULT_PORT,
        client_id: int = IBKR_DEFAULT_CLIENT_ID,
        exchange: str = "SMART",
        currency: str = "USD",
        market_data_timeout: float = 8.0,
    ) -> None:
        try:
            from ib_async import IB
        except ImportError as exc:  # keeps the yahoo path dependency-free
            raise ImportError("--source ibkr needs `pip install ib_async`") from exc

        self._ib = IB()
        # readonly rules out any order being placed from a scanning session.
        self._ib.connect(host, port, clientId=client_id, readonly=True)
        self._exchange = exchange
        self._currency = currency
        self._timeout = market_data_timeout
        self._underlyings: dict[str, object] = {}
        self._chains: dict[str, object] = {}

    def close(self) -> None:
        if self._ib.isConnected():
            self._ib.disconnect()

    def __enter__(self) -> "IBKRProvider":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _underlying(self, ticker: str):
        if ticker not in self._underlyings:
            from ib_async import Stock

            contract = Stock(ticker, self._exchange, self._currency)
            qualified = self._ib.qualifyContracts(contract)
            if not qualified:
                raise ValueError(f"IBKR could not qualify underlying {ticker}")
            self._underlyings[ticker] = qualified[0]
        return self._underlyings[ticker]

    def _chain(self, ticker: str):
        if ticker not in self._chains:
            underlying = self._underlying(ticker)
            params = self._ib.reqSecDefOptParams(
                underlying.symbol, "", underlying.secType, underlying.conId
            )
            smart = [p for p in params if p.exchange == self._exchange] or list(params)
            if not smart:
                raise ValueError(f"IBKR returned no option parameters for {ticker}")
            self._chains[ticker] = smart[0]
        return self._chains[ticker]

    def spot(self, ticker: str) -> Optional[float]:
        [snapshot] = self._ib.reqTickers(self._underlying(ticker))
        price = as_float(snapshot.marketPrice())
        if price <= 0.0:
            price = as_float(snapshot.close)
        return price or None

    def dividend_yield(self, ticker: str) -> float:
        """Unused for IBKR: its model greeks already price in the dividend stream."""
        return 0.0

    def expirations(self, ticker: str) -> list[str]:
        return sorted(
            datetime.strptime(exp, "%Y%m%d").strftime("%Y-%m-%d")
            for exp in self._chain(ticker).expirations
        )

    def quotes(self, ticker: str, expiration: str) -> list[ContractQuote]:
        from ib_async import Option

        spot = self.spot(ticker) or 0.0
        if spot <= 0.0:
            return []

        chain = self._chain(ticker)
        ib_expiration = datetime.strptime(expiration, "%Y-%m-%d").strftime("%Y%m%d")
        strikes = [
            strike
            for strike in sorted(chain.strikes)
            if abs(strike - spot) / spot <= IBKR_STRIKE_WINDOW
        ]
        if not strikes:
            return []

        contracts = [
            Option(
                ticker,
                ib_expiration,
                strike,
                right,
                self._exchange,
                currency=self._currency,
                tradingClass=chain.tradingClass,
            )
            for strike in strikes
            for right in ("C", "P")
        ]
        contracts = self._ib.qualifyContracts(*contracts)
        if not contracts:
            return []

        # genericTickList 101 = option open interest, 106 = option implied volatility.
        tickers = [self._ib.reqMktData(contract, "101,106", False, False) for contract in contracts]
        self._ib.sleep(self._timeout)

        rows: list[ContractQuote] = []
        for contract, snapshot in zip(contracts, tickers):
            side: Side = "call" if contract.right.upper().startswith("C") else "put"
            model = snapshot.modelGreeks
            greeks = None
            iv = as_float(snapshot.impliedVolatility)
            if model is not None:
                iv = as_float(model.impliedVol, iv)
                greeks = BrokerGreeks(
                    delta=as_float(model.delta),
                    gamma=as_float(model.gamma),
                    # IBKR reports theta per calendar day already.
                    theta=as_float(model.theta),
                    # IBKR vega is per 1 volatility point, matching the scanner.
                    vega=as_float(model.vega),
                )
            open_interest = as_float(
                snapshot.callOpenInterest if side == "call" else snapshot.putOpenInterest
            )
            rows.append(
                ContractQuote(
                    side=side,
                    strike=as_float(contract.strike),
                    bid=as_float(snapshot.bid),
                    ask=as_float(snapshot.ask),
                    open_interest=int(open_interest),
                    volume=int(as_float(snapshot.volume)),
                    iv=iv,
                    contract_symbol=contract.localSymbol or f"{ticker}{ib_expiration}{contract.right}{contract.strike:g}",
                    greeks=greeks,
                )
            )
            self._ib.cancelMktData(contract)
        return rows


def build_provider(source: str, **ibkr_kwargs: object) -> ChainProvider:
    if source == "yahoo":
        return YahooProvider()
    if source == "ibkr":
        return IBKRProvider(**ibkr_kwargs)  # type: ignore[arg-type]
    raise ValueError(f"unknown chain source: {source}")
