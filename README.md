# India Trade Bot (NSE · Paper Trading)

Minimal Flask app that plays the role of a trading bot for the Indian market.
It scans a NIFTY 50 watchlist, runs a long-only moving-average-crossover
strategy and books paper trades at live (Kite) or simulated prices.

## What it does
- `bot/engine.py` – background loop that polls prices every 10s, evaluates
  the MA(9/21) crossover and enters/exits 5-lot paper positions.
- `bot/broker.py` – `KiteBroker` (live LTP via Zerodha Kite REST API when an
  access token is supplied) and `SimBroker` (fully offline random walk).
- `bot/market_hours.py` – NSE session guard (09:15–15:30 IST, Mon–Fri).
- `templates/index.html` – dashboard: start/stop, cash, P&L, positions,
  trade log.

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
| GET  | `/api/status` | snapshot of bot state |
| POST | `/api/start?sim=1` | start engine with SimBroker |
| POST | `/api/start?kite_token=<token>` | start engine with live LTP |
| POST | `/api/stop` | stop engine |
| POST | `/api/tick` | force one strategy pass |

## Safety
Paper trading only — order placement is intentionally out of scope. To wire
real order flow you would need broker credentials plus proper order,
margin and risk checks; do not treat this code as production-ready.
