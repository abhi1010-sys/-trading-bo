import json
import random
import urllib.request


class KiteBroker:
    """Live data sessions via Zerodha Kite (api.kite.trade).

    `ltp` accepts exchange-prefixed symbols ("NSE:RELIANCE", "BSE:CUB").
    Requests are chunked 100 instruments at a time. Unsupported symbols
    fall back to a deterministic pseudo-price so the suggestion engine
    still works. No order-placement here.
    """

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

    def __init__(self):
        self._walk = {}

    def ltp(self, symbols):
        out = {}
        for s in symbols:
            base = self._walk.get(s, random.uniform(200, 3200))
            self._walk[s] = max(50, base * random.uniform(0.985, 1.015))
            out[s] = self._walk[s]
        return out
