# SMC-XAUUSD

Trading tooling: an SMC signal-validation API for XAU/USD and an options greeks
alignment scanner for thinkorswim.

## Setup

```bash
pip install -r requirements.txt
```

## Options greeks alignment scanner

`greeks_alignment_scanner.py` pulls option chains, computes Black-Scholes greeks
from each contract's implied volatility, and ranks the contracts where delta,
gamma, theta and vega line up for a long call or long put.

```bash
python3 greeks_alignment_scanner.py SPY QQQ AAPL --min-dte 7 --max-dte 45 --top 10 --aligned-only
python3 greeks_alignment_scanner.py NVDA --side call --markdown-out report.md --json-out report.json
```

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

The score (0–100) weights delta centering 30%, gamma/theta 30%, theta burn 25%
and vega 15%. Contracts are quoted in thinkorswim symbol format (`.SPY260918P777`)
so they paste straight into the platform.

Quotes come from Yahoo Finance and are delayed; verify the quote and the greeks
in thinkorswim before placing an order. Not investment advice.

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
