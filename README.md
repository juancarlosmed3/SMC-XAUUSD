# SMC-XAUUSD

Trading tooling: an SMC signal-validation API for XAU/USD and an options greeks
alignment scanner for thinkorswim.

## Setup

```bash
pip install -r requirements.txt
# only needed for --source ibkr
pip install ib_async
```

## Options greeks alignment scanner

`greeks_alignment_scanner.py` pulls option chains and ranks the contracts where
delta, gamma, theta and vega line up for a long call or long put.

```bash
python3 greeks_alignment_scanner.py SPY QQQ AAPL --min-dte 7 --max-dte 45 --top 10 --aligned-only
python3 greeks_alignment_scanner.py NVDA --side call --markdown-out report.md --json-out report.json
python3 greeks_alignment_scanner.py SPY --source ibkr --ibkr-port 7497
```

### Data sources

| `--source` | Quotes | Greeks | Requirements |
|------------|--------|--------|--------------|
| `yahoo` (default) | Delayed ~15 min | Computed locally with Black-Scholes from the published IV | None |
| `ibkr` | Live | IBKR model greeks, used verbatim | `ib_async` plus a running, logged-in TWS or IB Gateway |

For IBKR, enable *Configure > API > Enable ActiveX and Socket Clients* and point
`--ibkr-port` at your instance: 7497 TWS paper, 7496 TWS live, 4002 Gateway
paper, 4001 Gateway live. The scanner connects read-only, so it can never place
an order. IBKR forces a re-login roughly daily, so an unattended schedule needs
IB Gateway kept alive (for example with IBC). Only strikes within 20% of spot
are requested, to stay under IBKR's market data line limit.

### Alignment bands

A contract is "aligned" only when every greek is inside its band:

| Greek | Band (default) | Why |
|-------|----------------|-----|
| Delta | 0.35–0.65 absolute | Real directional exposure without paying for deep ITM intrinsic |
| Gamma vs theta | gain on a one-sigma daily move >= 0.85x one day of decay | Convexity has to keep up with the rent you pay |
| Theta | <= 3.5% of premium per day | Caps the daily bleed while the thesis plays out |
| Vega | <= 0.30 per dollar of premium | Keeps a directional trade from becoming an IV bet |

Liquidity filters (open interest, volume, bid/ask spread, minimum premium) run
before the greeks so the ranked contracts are actually fillable. Every band is
overridable from the CLI (`--min-abs-delta`, `--max-theta-burn`, ...).

`--max-premium` caps the cash cost per contract (`--max-premium 6` means at most
$600). Expect the scores to drop as you lower it: a cheap contract is cheap
because it is further out of the money or closer to expiry, so its delta drifts
toward the edge of the band and its decay is a larger percentage of the premium.

The score (0–100) weights delta centering 30%, gamma/theta 30%, theta burn 25%
and vega 15%. Contracts are quoted in thinkorswim symbol format (`.SPY260918P777`)
so they paste straight into the platform.

Verify the quote and the greeks in thinkorswim before placing an order. Not
investment advice.

## SMC signal-validation API

`Qwen_python_20251111_qg1ocrn27-SMC-XAUUSD.py` exposes a FastAPI service that
validates XAU/USD scalping signals against multi-timeframe POC alignment.

```bash
uvicorn Qwen_python_20251111_qg1ocrn27-SMC-XAUUSD:app --reload
```

## Tests

```bash
python3 -m pytest tests/
```
