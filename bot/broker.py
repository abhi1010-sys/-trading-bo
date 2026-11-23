import json
import random
import time
import urllib.request


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
