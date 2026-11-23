"""Real-time suggestion engine for the Indian market (NSE + BSE).

Scans a tradable universe (see bot/universe.py) via a broker session
(Zerodha Kite if credentials exist, simulated otherwise), evaluates a
long-only MA(momentum) crossover per symbol and publishes actionable
suggestions with entry, stop-loss and target levels. It does NOT place
or simulate fills: execution is manual by design (suggestions only).
"""
import logging
import threading
import time as _time

from .market_hours import IST, is_market_open
from .universe import UNIVERSE

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

STRATEGY_PARAMS = {"fast": 9, "slow": 21}
STOP_PCT = 0.01   # 1% below entry (NSE intraday SL)
TARGET_PCT = 0.02 # 2% above entry (1:2 risk-reward)

_engine_lock = threading.Lock()


def split_key(sym):
    exch, _, short = sym.partition(":")
    return (exch or "NSE"), (short or sym)


class SuggestionEngine:
    """Manages the universe data feed and per-poll trading suggestions."""

    def __init__(self, broker):
        self.broker = broker
        self.symbols = list(UNIVERSE)
        self.params = dict(STRATEGY_PARAMS)
        self.priced = {}  # 'EXCHANGE:SYMBOL' -> last price
        self.history = {}  # 'EXCHANGE:SYMBOL' -> list of closes
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

    # ---------------- suggestions ----------------
    def _decision(self, sym):
        px = self.priced.get(sym)
        if not px:
            return None
        sig = self._signal(sym)
        exch, short = split_key(sym)
        if sig == 1:
            action = "BUY"
        elif sig == -1:
            action = "EXIT"
        else:
            action = "HOLD"
        fast, slow = self.params["fast"], self.params["slow"]
        h = self.history[sym]
        if len(h) >= slow:
            fma = sum(h[-fast:]) / fast
            sma = sum(h[-slow:]) / slow
            basis = f"MA{fast} {fma:.1f} vs MA{slow} {sma:.1f}"
        else:
            basis = f"warming up ({len(h)}/{slow} bars)"
        return {
            "exchange": exch,
            "symbol": short,
            "action": action,
            "price": round(px, 2),
            "entry": round(px, 2),
            "stop_loss": round(px * (1 - STOP_PCT), 2),
            "target": round(px * (1 + TARGET_PCT), 2),
            "basis": basis,
        }

    def signals(self):
        rows = [self._decision(s) for s in self.symbols]
        rows = [r for r in rows if r]
        priority = {"BUY": 0, "EXIT": 1, "HOLD": 2, "WAIT": 3}
        return sorted(rows, key=lambda r: (priority.get(r["action"], 9), r["exchange"], r["symbol"]))

    # ---------------- loop ----------------
    def step(self):
        if not is_market_open():
            self.status = "MARKET CLOSED (NSE/BSE 09:15-15:30 IST, Mon-Fri)"
            return
        self.status = "SCANNING"
        self._refresh_prices()

    def _run(self):
        while self.running:
            try:
                self.step()
            except Exception:
                log.exception("engine step failed")
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
        polled = sum(len(h) for h in self.history.values())
        return {
            "running": self.running,
            "status": self.status,
            "market_open": is_market_open(),
            "suggestions_only": True,
            "universe_size": len(self.symbols),
            "by_exchange": _count_by_exchange(self.symbols),
            "bars_polled": polled,
            "quotes": {s: round(v, 2) for s, v in self.priced.items()},
            "signals": self.signals(),
        }


def _count_by_exchange(symbols):
    counts = {}
    for s in symbols:
        exch = split_key(s)[0]
        counts[exch] = counts.get(exch, 0) + 1
    return counts


_engine = None


def init_engine(broker):
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = SuggestionEngine(broker)
    return _engine


def get_engine():
    return _engine
