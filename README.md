# India Trade Bot (NSE + BSE · Institutional Model Book)

Minimal Flask app that runs an institutional-style simulated model book
over a NSE + BSE universe and publishes real-time trade suggestions with
entry, stop-loss and target levels. Real broker orders are never placed.

## What it does
- `bot/universe.py` – tradable universe as `EXCHANGE:SYMBOL` keys:
  Nifty 50, a Nifty Next 100 subset and a BSE midcap subset. Edit freely;
  keep sizes reasonable for API rate limits.
- `bot/engine.py` – institutional-style model book (₹25 Cr, simulated):
  MA(20/100) trend entries, risk-based sizing (0.5% of NAV per position,
  4% NAV position cap at entry; weights drift with prices), max 25
  positions, 20% cash floor, 5% stop-losses
  and 15% targets (1:3 risk-reward), plus a suggestions table with the
  MA basis behind each call. Model fills only.
- `bot/broker.py` – `KiteBroker` (live LTP via Zerodha Kite REST API,
  chunked 100 instruments per request) and `SimBroker` (fully offline).
- `bot/market_hours.py` – NSE/BSE session guard (09:15–15:30 IST, Mon–Fri).
- `templates/index.html` – dashboard: scanner start/stop, universe stats,
  signals table.
- `demo.html` – standalone in-browser demo of the same dashboard
  (no Python needed; open directly in a browser).

## Run
```bash
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

## Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/` | dashboard |
| GET  | `/api/status` | snapshot: universe stats + signals |
| POST | `/api/start?sim=1` | start scanner with SimBroker |
| POST | `/api/start?kite_token=<token>` | start with live NSE+BSE quotes |
| POST | `/api/stop` | stop scanner |
| POST | `/api/tick` | force one scan pass |

`/api/status` and `/api/tick` snapshots include a `signals` array:
`{exchange, symbol, action: BUY|EXIT|HOLD, price, entry, stop_loss, target,
basis}` sorted with actionable (`BUY`/`EXIT`) rows first.

## Safety
The book is simulated ("model") - no order placement, no broker execution.
Signals come from a simple moving-average crossover and are not investment
advice. Route any real orders manually through your broker and do so only
after your own research; algo trading in India is SEBI-regulated.
