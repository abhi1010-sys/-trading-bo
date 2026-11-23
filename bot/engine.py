"""Live paper-trading bot for the Indian market.

Trades NIFTY 50 stocks via a broker session (Zerodha Kite if credentials
exist), deploying a fixed capital per trade. Runs a background thread that
on each poll: refreshes prices through the broker adapter, evaluates the
long-only MA(momentum) crossover strategy for each watchlist symbol and
enters/exits paper positions accordingly. All fills are simulated at LTP
(slippage-free) - real order placement is intentionally out of scope.
"""
import logging
import threading
import time as _time
from datetime import datetime

from .market_hours import IST, now_ist, is_market_open

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

# NIFTY 50 watchlist (sample)
WATCHLIST = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
             "SBIN", "ITC", "LT", "BHARTIARTL", "HINDUNILVR"]

STRATEGY_PARAMS = {"fast": 9, "slow": 21, "qty": 5}
CASH = 1_000_000.0  # paper capital

_engine_lock = threading.Lock()


class LiveTradingEngine:
    """Manages watchlist data, paper positions and the bot loop."""

    def __init__(self, broker):
        self.broker = broker
        self.symbols = list(WATCHLIST)
        self.params = dict(STRATEGY_PARAMS)
        self.cash = CASH
        self.positions = {}  # symbol -> dict
        self.trade_log = []
        self.priced = {}  # symbol -> last price
        self.history = {}  # symbol -> list of closes
        self.running = False
        self.status = "STANDBY"
        self._thread = None

    # ---------------- data ----------------
    def _refresh_prices(self):
        quotes = self.broker.ltp(self.symbols)
        for sym in self.symbols:
            px = quotes.get(sym) or self.priced.get(sym)
            if px:
                self.priced[sym] = float(px)
                self.history.setdefault(sym, []).append(float(px))
                self.history[sym] = self.history[sym][-100:]

    # ---------------- strategy ----------------
    def _signal(self, sym):
        h = self.history[sym]
        fast, slow = self.params["fast"], self.params["slow"]
        if len(h) < slow:
            return 0
        fma = sum(h[-fast:]) / fast
        sma = sum(h[-slow:]) / slow
        prev_fma = sum(h[-fast - 1:-1]) / fast
        prev_sma = sum(h[-slow - 1:-1]) / slow
        cross_up = prev_fma <= prev_sma and fma > sma
        cross_dn = prev_fma >= prev_sma and fma < sma
        if cross_up:
            return 1
        if cross_dn:
            return -1
        return 0

    # ---------------- orders (paper) ----------------
    def _buy(self, sym, px):
        qty = self.params["qty"]
        cost = qty * px
        if cost > self.cash:
            return
        self.cash -= cost
        self.positions[sym] = {"qty": qty, "entry": px, "time": datetime.now(IST).isoformat()}
        self.trade_log.append(self._log("BUY", sym, qty, px))
        log.info("BUY %s x%d @ %.2f", sym, qty, px)

    def _sell(self, sym, px):
        pos = self.positions.pop(sym)
        self.cash += pos["qty"] * px
        self.trade_log.append(self._log("SELL", sym, pos["qty"], px,
                                        pnl=(px - pos["entry"]) * pos["qty"]))
        log.info("SELL %s x%d @ %.2f pnl %.2f", sym, pos["qty"], px,
                 (px - pos["entry"]) * pos["qty"])

    @staticmethod
    def _log(side, sym, qty, px, pnl=None):
        d = {"time": datetime.now(IST).strftime("%H:%M:%S"),
             "side": side, "symbol": sym, "qty": qty, "price": round(px, 2)}
        if pnl is not None:
            d["pnl"] = round(pnl, 2)
        return d

    # ---------------- loop ----------------
    def step(self):
        if not is_market_open():
            self.status = "MARKET CLOSED (NSE 09:15-15:30 IST, Mon-Fri)"
            return
        self.status = "SCANNING"
        self._refresh_prices()
        for sym in list(self.positions):
            if self._signal(sym) == -1:
                self._sell(sym, self.priced[sym])
        for sym in self.symbols:
            if sym not in self.positions and self._signal(sym) == 1:
                self._buy(sym, self.priced[sym])

    def _run(self):
        while self.running:
            try:
                self.step()
            except Exception:
                log.exception("bot step failed")
            _time.sleep(10)

    def start(self):
        if self.running:
            return
        self.running = True
        self.status = "BOOTING"
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        self.status = "STOPPED"

    # ---------------- reporting ----------------
    def snapshot(self):
        holdings, invested, unrealised = [], 0.0, 0.0
        for sym, p in self.positions.items():
            px = self.priced.get(sym, p["entry"])
            invested += p["qty"] * p["entry"]
            unrealised += (px - p["entry"]) * p["qty"]
            holdings.append({
                "symbol": sym, "qty": p["qty"], "entry": round(p["entry"], 2),
                "ltp": round(px, 2),
                "pnl": round((px - p["entry"]) * p["qty"], 2),
            })
        return {
            "running": self.running,
            "status": self.status,
            "market_open": is_market_open(),
            "cash": round(self.cash, 2),
            "invested": round(invested, 2),
            "unrealised_pnl": round(unrealised, 2),
            "total_value": round(self.cash + invested, 2),
            "positions": holdings,
            "trades": list(reversed(self.trade_log[-30:])),
            "quotes": {s: round(v, 2) for s, v in self.priced.items()},
        }


_engine = None


def init_engine(broker):
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = LiveTradingEngine(broker)
    return _engine


def get_engine():
    return _engine
