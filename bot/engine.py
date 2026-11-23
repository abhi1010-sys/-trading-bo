"""Institutional-style model portfolio engine for the Indian market (NSE + BSE).

Runs a medium-term trend model (MA fast/slow crossover) over the universe
in bot/universe.py as a simulated ("model") institutional book:

- Risk-based sizing: each position risks RISK_PCT of NAV at its stop level,
  capped at MAX_WEIGHT of NAV; integer share quantities.
- Portfolio limits: MAX_POSITIONS, cash floor of MIN_CASH_PCT of NAV.
- Exits: bearish crossover or stop-loss breach; targets displayed at +TGT.
- Model fills only: no broker orders are ever placed.

Snapshot carries NAV, cash, exposure, holdings with weights, model fills
and per-symbol suggestions with entry / stop / target levels.
"""
import logging
import threading
import time as _time
from datetime import datetime

from .market_hours import IST, is_market_open
from .universe import UNIVERSE

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

STRATEGY_PARAMS = {"fast": 20, "slow": 100}   # medium-term trend; warm-up 100 bars
STOP_PCT = 0.05      # 5% below entry
TARGET_PCT = 0.15    # 15% above entry (1:3 risk-reward)
RISK_PCT = 0.005     # 0.5% of NAV risked per position
MAX_POSITIONS = 25
MAX_WEIGHT = 0.04    # 4% NAV per position
MIN_CASH_PCT = 0.20  # keep 20% of NAV in cash
NAV_START = 250_000_000.0  # ₹25 Cr model book

_engine_lock = threading.Lock()


def split_key(sym):
    exch, _, short = sym.partition(":")
    return (exch or "NSE"), (short or sym)


class InstitutionalEngine:
    """Manages the universe feed, the model book and portfolio suggestions."""

    def __init__(self, broker):
        self.broker = broker
        self.symbols = list(UNIVERSE)
        self.params = dict(STRATEGY_PARAMS)
        self.cash = NAV_START
        self.positions = {}  # 'EXCHANGE:SYMBOL' -> {qty, entry}
        self.trade_log = []
        self.priced = {}
        self.history = {}  # capped at SLOW*3 bars
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
                self.history[sym] = self.history[sym][-300:]

    # ---------------- book ----------------
    def nav(self):
        return self.cash + sum(p["qty"] * self.priced.get(s, p["entry"])
                               for s, p in self.positions.items())

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

    def _sizing(self, entry):
        nav = self.nav()
        risk_amt = nav * RISK_PCT
        stop_dist = entry * STOP_PCT
        qty = int(risk_amt / stop_dist) if stop_dist > 0 else 0
        qty = min(qty, int(nav * MAX_WEIGHT / entry))
        return max(qty, 0)

    def _buy(self, sym, px):
        qty = self._sizing(px)
        cost = qty * px
        nav = self.nav()
        if qty < 1 or cost > self.cash or self.cash - cost < nav * MIN_CASH_PCT:
            return
        if len(self.positions) >= MAX_POSITIONS:
            return
        self.cash -= cost
        self.positions[sym] = {"qty": qty, "entry": px}
        self.trade_log.append(self._log("BUY", sym, qty, px))
        log.info("MODEL BUY %s x%d @ %.2f", sym, qty, px)

    def _sell(self, sym, px, reason):
        pos = self.positions.pop(sym)
        self.cash += pos["qty"] * px
        self.trade_log.append(self._log("SELL", sym, pos["qty"], px,
                                        pnl=(px - pos["entry"]) * pos["qty"],
                                        reason=reason))
        log.info("MODEL SELL %s x%d @ %.2f (%s)", sym, pos["qty"], px, reason)

    @staticmethod
    def _log(side, sym, qty, px, pnl=None, reason=None):
        exch, short = split_key(sym)
        d = {"time": datetime.now(IST).strftime("%H:%M:%S"), "side": side, "exchange": exch,
             "symbol": short, "qty": qty, "price": round(px, 2)}
        if pnl is not None:
            d["pnl"] = round(pnl, 2)
        if reason:
            d["reason"] = reason
        return d

    # ---------------- suggestions ----------------
    def _decision(self, sym):
        px = self.priced.get(sym)
        if not px:
            return None
        exch, short = split_key(sym)
        pos = self.positions.get(sym)
        entry = pos["entry"] if pos else px
        stop_hit = bool(pos) and px <= entry * (1 - STOP_PCT)
        sig = self._signal(sym)
        if pos and (stop_hit or sig == -1):
            action = "EXIT"
        elif not pos and sig == 1:
            action = "BUY"
        elif pos:
            action = "HOLD"
        else:
            action = "WAIT"
        fast, slow = self.params["fast"], self.params["slow"]
        h = self.history[sym]
        if len(h) >= slow:
            fma = sum(h[-fast:]) / fast
            sma = sum(h[-slow:]) / slow
            basis = f"MA{fast} {fma:.1f} vs MA{slow} {sma:.1f}"
        else:
            basis = f"warming up ({len(h)}/{slow} bars)"
        nav = self.nav()
        qty = self._sizing(px)
        return {
            "exchange": exch,
            "symbol": short,
            "action": action,
            "price": round(px, 2),
            "entry": round(entry, 2),
            "stop_loss": round(entry * (1 - STOP_PCT), 2),
            "target": round(entry * (1 + TARGET_PCT), 2),
            "suggested_qty": qty,
            "model_weight": round(pos["qty"] * px / nav, 4) if pos else 0.0,
            "basis": basis,
        }

    def signals(self):
        rows = [self._decision(s) for s in self.symbols]
        rows = [r for r in rows if r]
        priority = {"EXIT": 0, "BUY": 1, "HOLD": 2, "WAIT": 3}
        return sorted(rows, key=lambda r: (priority.get(r["action"], 9), r["exchange"], r["symbol"]))

    # ---------------- loop ----------------
    def step(self):
        if not is_market_open():
            self.status = "MARKET CLOSED (NSE/BSE 09:15-15:30 IST, Mon-Fri)"
            return
        self.status = "SCANNING"
        self._refresh_prices()
        for sym in list(self.positions):
            px = self.priced[sym]
            if px <= self.positions[sym]["entry"] * (1 - STOP_PCT):
                self._sell(sym, px, "stop-loss")
            elif self._signal(sym) == -1:
                self._sell(sym, px, "trend break")
        for sym in self.symbols:
            if sym not in self.positions and self._signal(sym) == 1:
                self._buy(sym, self.priced[sym])
        self.status = "SCANNED"

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
        nav = self.nav()
        invested = sum(p["qty"] * self.priced.get(s, p["entry"]) for s, p in self.positions.items())
        holdings = []
        for sym, p in self.positions.items():
            px = self.priced.get(sym, p["entry"])
            exch, short = split_key(sym)
            holdings.append({
                "exchange": exch, "symbol": short, "qty": p["qty"],
                "entry": round(p["entry"], 2), "ltp": round(px, 2),
                "weight": round(p["qty"] * px / nav, 4),
                "pnl": round((px - p["entry"]) * p["qty"], 2),
                "stop_loss": round(p["entry"] * (1 - STOP_PCT), 2),
                "target": round(p["entry"] * (1 + TARGET_PCT), 2),
            })
        holdings.sort(key=lambda r: r["weight"], reverse=True)
        return {
            "running": self.running,
            "status": self.status,
            "market_open": is_market_open(),
            "mode": "institutional-model",
            "universe_size": len(self.symbols),
            "by_exchange": _count_by_exchange(self.symbols),
            "nav": round(nav, 2),
            "cash": round(self.cash, 2),
            "invested": round(invested, 2),
            "exposure": round(invested / nav, 4) if nav else 0.0,
            "positions": holdings,
            "trades": list(reversed(self.trade_log[-40:])),
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
            _engine = InstitutionalEngine(broker)
    return _engine


def get_engine():
    return _engine
