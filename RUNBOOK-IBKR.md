# Running the scanner against your own TWS (live data)

Everything here runs on **your** machine, against the TWS you are already logged
into. No credentials leave your PC and the scanner connects read-only, so it
cannot place, modify or cancel an order.

## 1. Configure TWS once

In TWS: **File > Global Configuration > API > Settings**

- Check **Enable ActiveX and Socket Clients**.
- Leave **Read-Only API** checked (the scanner never needs write access).
- Note the **Socket port**: `7496` for a live login, `7497` for paper.
- Trusted IPs should include `127.0.0.1` (default).
- Uncheck **Download open orders on connection** if TWS complains about it.

Then click OK and leave TWS running and logged in.

## 2. Install the scanner

```bash
git clone https://github.com/juancarlosmed3/SMC-XAUUSD.git
cd SMC-XAUUSD
pip install -r requirements.txt
pip install ib_async
```

Windows: use `py -m pip install ...` if `pip` is not on your PATH.

## 3. Check the connection

```bash
python3 greeks_alignment_scanner.py AMZN --source ibkr --ibkr-port 7496 --min-dte 7 --max-dte 45
```

- If it prints a table, you are done.
- `cannot reach IBKR at 127.0.0.1:7496` means TWS is closed, not logged in, or
  the socket port is different — recheck step 1.
- A TWS popup asking to accept an incoming connection: accept it and tick
  "don't ask again for this client".

## 4. The scans

```bash
# your watchlist, calls and puts, 7-45 DTE
python3 greeks_alignment_scanner.py AAPL MSFT GOOGL AMZN NVDA META TSLA \
  --source ibkr --ibkr-port 7496 \
  --min-dte 7 --max-dte 45 --top 12 --aligned-only \
  --markdown-out report.md --json-out report.json

# same thing capped at $600 per contract
python3 greeks_alignment_scanner.py AAPL MSFT GOOGL AMZN NVDA META TSLA \
  --source ibkr --ibkr-port 7496 --max-premium 6 \
  --min-dte 7 --max-dte 45 --top 12 --aligned-only

# a single name, calls only
python3 greeks_alignment_scanner.py AMZN --source ibkr --ibkr-port 7496 --side call
```

`report.md` is the table with thinkorswim symbols; `report.json` is the same rows
as data. Paste either back to me and I will read the greeks with you.

## Notes

- With `--source ibkr` the greeks are IBKR's own `modelGreeks`, not estimates:
  delta, gamma, theta (per calendar day), vega (per volatility point) and IV come
  straight from the platform.
- One username can only hold one session, so this uses the TWS you already have
  open rather than logging in a second time.
- Only strikes within 20% of spot are requested, to stay under IBKR's market data
  line limit. A 7-ticker scan takes a couple of minutes.
- If a ticker returns nothing, it usually means no market data subscription for
  that product on your account — the run continues and lists the failure.
