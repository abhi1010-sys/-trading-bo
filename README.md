# India Trade Bot (NSE + BSE · Institutional Model Book)

Minimal Flask app that runs an institutional-style simulated model book
over a NSE + BSE universe and publishes real-time trade suggestions with
entry, stop-loss and target levels. Real broker orders are never placed.

## Pure web version — no Python, no install
- `web.html` — the same institutional model book as a single self-contained
  browser page. Just open the file, no install, no server, no Python.
  It seeds MA history from 1 year of daily bars and streams prices (Yahoo
  Finance, ~15-min delayed; where the browser cannot fetch directly it
  transparently relays via a public CORS proxy, labelled honestly), falls
  back to clearly-labelled simulated demo data if no relay is reachable —
  never silently — and remembers your model book between visits
  (localStorage; "Reset book" to start fresh). Same ₹25 Cr NAV, risk
  sizing, 4% weights, 5% stops / 15% targets, suggestions only.
  Tip: host it free on GitHub Pages — Settings → Pages → Deploy from
  branch: main / root — then it is a website on your phone too.

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
- `bot/broker.py` – three feeds: `YahooBroker` (default; free real NSE/BSE
  prices via Yahoo Finance chart API, ~15-min delayed, plus 1-year daily
  history that seeds the MA(100) instantly), `KiteBroker` (real-time Kite
  REST when you pass a token; chunked 100 instruments per request) and
  `SimBroker` (offline demo via `/api/start?sim=1`).
- `bot/market_hours.py` – NSE/BSE session guard (09:15–15:30 IST, Mon–Fri).
- `templates/index.html` – dashboard: scanner start/stop, universe stats,
  signals table.
- `demo.html` – standalone in-browser demo (30-symbol sample; kept for
  reference — `web.html` is the current pure-web version).

## Run
```bash
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000 and press Run Fund. First start warms up by
pulling ~1 year of daily closes per symbol (~1-2 min for 166 symbols;
status shows "WARMING UP"), after which detailed entry / stop / target
levels are published on real prices even outside market hours (levels on
last close; the model book itself only fills during NSE/BSE hours).

## Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/` | dashboard |
| GET  | `/api/status` | snapshot: universe stats + signals |
| POST | `/api/start` | start with live Yahoo feed (default) |
| POST | `/api/start?sim=1` | start offline with simulated prices |
| POST | `/api/start?kite_token=<token>` | start with live NSE+BSE quotes |
| POST | `/api/stop` | stop scanner |
| POST | `/api/tick` | force one scan pass |

`/api/status` and `/api/tick` snapshots include a `signals` array:
`{exchange, symbol, action: BUY|EXIT|HOLD, price, entry, stop_loss, target,
basis}` sorted with actionable (`BUY`/`EXIT`) rows first.

## Zero-delay (real-time) ticks
The default Yahoo feed is real data but ~15-min delayed. Two real-time
routes are supported:

**Sharekhan (your broker, free):**
1. Generate an API key at [sharekhan.com/trading-api](https://www.sharekhan.com/trading-api)
   (free; standard brokerage applies)
2. `export SHAREKHAN_API_KEY=... SHAREKHAN_SECRET_KEY=...`
3. `python scripts/sharekhan_login.py` (per-session; repeat each market day)
4. `SHAREKHAN_API_KEY=... SHAREKHAN_ACCESS_TOKEN=... python app.py`

Notes: the engine subscribes the whole universe on
`wss://stream.sharekhan.com` and falls back to the delayed Yahoo feed
while ticks are absent (never to silent simulation). The vendor SDK
ships its binary tick parser as an unimplemented stub, so JSON frames
parse out of the box; for raw binary frames pass a
`binary_tick_parser` callable to `SharekhanBroker`.

**Zerodha Kite Connect (paid ~₹2,000/mo):**
1. `export KITE_API_KEY=... KITE_API_SECRET=...`
2. `python scripts/kite_login.py` (repeat daily - tokens expire)
3. `KITE_API_KEY=... KITE_ACCESS_TOKEN=... python app.py`

Either way the engine drops to 5s decision cycles and the dashboard
shows the effective data source in real time.

## Safety
The book is simulated ("model") - no order placement, no broker execution.
Signals come from a simple moving-average crossover and are not investment
advice. Route any real orders manually through your broker and do so only
after your own research; algo trading in India is SEBI-regulated.
