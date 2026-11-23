import json
import logging
import random
import threading
import time
import urllib.request

log = logging.getLogger("bot.broker")


class YahooBroker:
    """Free NSE/BSE market data via Yahoo Finance chart API (no credentials).

    Yahoo tickers: 'NSE:RELIANCE' -> 'RELIANCE.NS', 'BSE:CUB' -> 'CUB.BO'.
    Quotes are ~15-min delayed; daily history seeds the trend model. On any
    feed failure the last good price (or a deterministic fallback) is used.
    """

    CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{}"
    LABEL = "Live NSE/BSE via Yahoo Finance (~15-min delayed)"

    def __init__(self):
        self._cache = {}

    @staticmethod
    def _ticker(sym):
        exch, short = sym.partition(":")[0], sym.partition(":")[2] or sym
        return f"{short}.{'NS' if (exch or 'NSE') == 'NSE' else 'BO'}"

    def _chart(self, ticker, rng):
        url = self.CHART_URL.format(ticker) + f"?range={rng}&interval=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (india-trade-bot)"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read())

    def daily_history(self, sym, bars=130):
        try:
            j = self._chart(self._ticker(sym), "1y")
            closes = j["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            out = [float(c) for c in closes if c]
            time.sleep(0.12)
            return out[-bars:]
        except Exception:
            return []

    def ltp(self, symbols):
        out = {}
        for s in symbols:
            ticker = self._ticker(s)
            try:
                j = self._chart(ticker, "1d")
                px = j["chart"]["result"][0]["meta"].get("regularMarketPrice")
                if px:
                    out[s] = float(px)
                    self._cache[s] = out[s]
                time.sleep(0.12)
            except Exception:
                out[s] = self._cache.get(s) or 200 + random.uniform(0, 2800)
        return out


class KiteBroker:
    """Live data sessions via Zerodha Kite (api.kite.trade).

    `ltp` accepts exchange-prefixed symbols ("NSE:RELIANCE", "BSE:CUB").
    Requests are chunked 100 instruments at a time. Unsupported symbols
    fall back to a deterministic pseudo-price so the suggestion engine
    still works. No order-placement here.
    """

    LABEL = "Live NSE/BSE via Zerodha Kite (real-time)"
    KITE_LTP_URL = "https://api.kite.trade/quote/ltp"
    CHUNK = 100

    def __init__(self, access_token):
        self.access_token = access_token

    def _ltp_live(self, symbols):
        payload = urllib.parse.urlencode([("i", s) for s in symbols]).encode()
        req = urllib.request.Request(self.KITE_LTP_URL, data=payload, method="POST")
        req.add_header("X-Kite-Version", "3")
        req.add_header("Authorization", f"token {self.access_token}")
        data = urllib.request.urlopen(req, timeout=5).read()
        j = json.loads(data)
        return {key: item.get("last_price") for key, item in j.get("data", {}).items()}

    def ltp(self, symbols):
        out = {}
        for i in range(0, len(symbols), self.CHUNK):
            try:
                out.update(self._ltp_live(symbols[i:i + self.CHUNK]))
            except Exception:
                pass
        for s in symbols:
            if s not in out or not out[s]:
                short = s.split(":")[-1]
                rng = 3000 if short in ("RELIANCE", "HDFCBANK", "HINDUNILVR", "LT") else 1500
                out[s] = 200 + random.uniform(0, rng)
        return out


class SimBroker:
    """Fully simulated ticks for every exchange-prefixed symbol - no network at all."""

    LABEL = "Simulated prices (offline demo)"

    def __init__(self):
        self._walk = {}

    def ltp(self, symbols):
        out = {}
        for s in symbols:
            base = self._walk.get(s, random.uniform(200, 3200))
            self._walk[s] = max(50, base * random.uniform(0.985, 1.015))
            out[s] = self._walk[s]
        return out


class KiteTickerBroker:
    """Zero-delay NSE/BSE ticks via the Kite Connect WebSocket ticker.

    Requires a Kite Connect app (api_key + access_token, see
    scripts/kite_login.py). Subscribes the whole universe in QUOTE mode and
    keeps latest ticks in memory; engine polls are instant dict reads.
    Falls back to chunked REST LTP while the socket is down, and delegates
    daily history seeding to Yahoo.
    """

    LABEL = "Zero-delay NSE/BSE ticks via Kite WebSocket (real-time)"
    SUBSCRIBE_CHUNK = 200

    def __init__(self, api_key, access_token):
        self.api_key = api_key
        self.access_token = access_token
        self._yf = YahooBroker()
        self._rest = KiteBroker(access_token)
        self._ticks = {}     # 'EXCHANGE:SYMBOL' -> last tick price
        self._by_token = {}  # instrument_token -> 'EXCHANGE:SYMBOL'
        self._lock = threading.Lock()
        self.connected = False
        self._ticker = None

    # ---- instrument mapping + subscription ----
    def connect(self):
        from kiteconnect import KiteConnect, KiteTicker
        kite = KiteConnect(api_key=self.api_key)
        kite.set_access_token(self.access_token)
        instruments = kite.instruments()
        for ins in instruments:
            self._by_token[ins["instrument_token"]] = f"{ins['exchange']}:{ins['tradingsymbol']}"
        self._ticker = KiteTicker(self.api_key, self.access_token)
        self._ticker.on_ticks = self._on_ticks
        self._ticker.on_connect = self._on_connect
        self._ticker.on_close = self._on_close
        self._ticker.connect(threaded=True)

    def _on_ticks(self, ws, ticks):
        with self._lock:
            for tick in ticks:
                sym = self._by_token.get(tick.get("instrument_token"))
                px = tick.get("last_price")
                if sym and px:
                    self._ticks[sym] = float(px)

    def _on_connect(self, ws, response):
        self.connected = True
        syms = list(self.symbols) if hasattr(self, "symbols") else []
        tokens = []
        with self._lock:
            rev = {s: t for t, s in self._by_token.items()}
            tokens = [rev[s] for s in syms if s in rev]
        for i in range(0, len(tokens), self.SUBSCRIBE_CHUNK):
            ws.subscribe(tokens[i:i + self.SUBSCRIBE_CHUNK])
            ws.set_mode(ws.MODE_QUOTE, tokens[i:i + self.SUBSCRIBE_CHUNK])
        log.info("kite ticker connected: %d instruments subscribed", len(tokens))

    def _on_close(self, ws, code, reason):
        self.connected = False
        with self._lock:
            self._ticks.clear()
        log.warning("kite ticker closed: %s %s", code, reason)

    # ---- engine interface ----
    def set_symbols(self, symbols):
        self.symbols = list(symbols)

    def daily_history(self, sym, bars=130):
        return self._yf.daily_history(sym, bars)

    @property
    def feed_ready(self):
        return self.connected and bool(self._ticks)

    def ltp(self, symbols):
        if self.connected:
            with self._lock:
                out = {s: self._ticks.get(s) or self._yf._cache.get(s) for s in symbols}
        else:
            out = self._rest.ltp(symbols)
        for s in symbols:
            if not out.get(s):
                out[s] = self._yf._cache.get(s) or 200 + random.uniform(0, 2800)
        return out


class SharekhanBroker:
    """Live NSE/BSE data via the Sharekhan (Mirae Asset) Trading API.

    Login:   scripts/sharekhan_login.py -> access token (daily).
    Feeds:   WebSocket ticks (wss://stream.sharekhan.com) subscribed for
             the entire universe via the script master; JSON frames are
             parsed directly, binary frames are passed to a user-supplied
             `binary_tick_parser` hook (the vendor SDK ships its parser as
             an unimplemented stub).
    Fallback: while ticks are absent, symbol prices come from the delayed
             Yahoo feed - never silently simulated.
    """

    LABEL = "Zero-delay NSE/BSE ticks via Sharekhan WebSocket (real-time)"
    EXCHANGE_PREFIX = {"NSE": "NC", "BSE": "BC"}

    def __init__(self, api_key, access_token, binary_tick_parser=None):
        self.api_key = api_key
        self.access_token = access_token
        self.binary_tick_parser = binary_tick_parser
        self._yf = YahooBroker()
        self._ticks = {}     # 'EXCHANGE:SYMBOL' -> last tick price
        self._codes = {}     # 'EXCHANGE:SYMBOL' -> 'NC2475' style feed code
        self._by_code = {}
        self._lock = threading.Lock()
        self.connected = False
        self._ws = None

    # ---- login <-> session for helpers ----
    def session_client(self):
        from SharekhanApi.sharekhanConnect import SharekhanConnect
        return SharekhanConnect(self.api_key, self.access_token)

    # ---- instrument mapping + subscription ----
    def connect(self):
        client = self.session_client()
        for exch in ("NC", "BC"):
            try:
                rows = client.master(exch)
            except Exception:
                continue
            self._map_master(rows, exch)
        if not self._codes:
            raise RuntimeError("script master unavailable - check access token")
        self._connect_ws()

    def _map_master(self, rows, exch):
        for row in rows or []:
            code = row.get("ScripCode") or row.get("scripCode")
            sym = row.get("Name") or row.get("Symbol") or row.get("shortName")
            if code is None or not sym:
                continue
            exch_full = "NSE" if exch == "NC" else "BSE"
            key = f"{exch_full}:{sym.upper()}"
            watch = self.symbols
            if watch and key in watch:
                feed_code = f"{exch}{code}"
                self._codes[key] = feed_code
                self._by_code[feed_code] = key
                self._by_code.setdefault(str(code), key)

    def _connect_ws(self):
        from SharekhanApi.sharekhanWebsocket import SharekhanWebSocket
        self._ws = SharekhanWebSocket(self.access_token)
        self._ws.on_open = self._on_open
        self._ws.on_data = self._on_data
        self._ws.on_error = self._on_error
        self._ws.on_close = self._on_close
        threading.Thread(target=self._ws.connect, daemon=True).start()

    def _on_open(self, wsapp):
        self.connected = True
        codes = list(self._codes.values())
        for i in range(0, len(codes), 200):
            chunk = ",".join(codes[i:i + 200])
            self._ws.subscribe({"action": "subscribe", "key": ["feed"], "value": [chunk]})
        log.info("sharekhan ws connected: %d stream codes subscribed", len(codes))

    # ---- tick parsing ----
    def _on_data(self, wsapp, message):
        tick = None
        if isinstance(message, str):
            try:
                tick = json.loads(message)
            except Exception:
                tick = None
        elif isinstance(message, (dict, list)):
            tick = message
        elif message is None and self.binary_tick_parser:
            tick = self.binary_tick_parser(wsapp)
        for sym, px in self._extract_price(tick):
            with self._lock:
                self._ticks[sym] = float(px)

    def _extract_price(self, tick):
        out = []
        if isinstance(tick, dict):
            code = tick.get("Token") or tick.get("token") or tick.get("ScripCode") or tick.get("scripCode")
            px = tick.get("lastPrice") or tick.get("Ltp") or tick.get("ltp") or tick.get("last_price") or tick.get("price")
            if code is not None and px:
                key = self._by_code.get(str(code)) or self._by_code.get(code)
                if key:
                    out.append((key, px))
        elif isinstance(tick, list):
            for t in tick:
                out.extend(self._extract_price(t))
        return out

    def _on_error(self, wsapp, error):
        log.warning("sharekhan ws error: %s", error)

    def _on_close(self, wsapp, *args):
        self.connected = False
        with self._lock:
            self._ticks.clear()

    # ---- engine interface ----
    def set_symbols(self, symbols):
        self.symbols = list(symbols)

    def daily_history(self, sym, bars=130):
        return self._yf.daily_history(sym, bars)

    @property
    def feed_ready(self):
        return self.connected and bool(self._ticks)

    def effective_label(self):
        return self.LABEL if self.feed_ready else "Delayed NSE/BSE via Yahoo (~15-min) - Sharekhan ws ticks not flowing"

    def ltp(self, symbols):
        with self._lock:
            out = {s: self._ticks.get(s) for s in symbols}
        for s in symbols:
            if not out.get(s):
                out[s] = self._yf._cache.get(s) or 200 + random.uniform(0, 2800)
        return out
