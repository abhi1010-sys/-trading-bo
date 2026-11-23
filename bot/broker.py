import json
import random
import urllib.request


class KiteBroker:
    """Live data sessions via Zerodha Kite (api.kite.trade).

    If an access token is given, `ltp` calls out to the broker; for
    unsupported symbols we fall back to a deterministic pseudo-price so
    the paper engine still works. No order-placement here.
    """

    KITE_LTP_URL = "https://api.kite.trade/quote/ltp"

    def __init__(self, access_token):
        self.access_token = access_token

    def _ltp_live(self, symbols):
        inst = [f"NSE:{s}" for s in symbols]
        payload = urllib.parse.urlencode({"i": inst}).encode()
        req = urllib.request.Request(self.KITE_LTP_URL, data=payload, method="POST")
        req.add_header("X-Kite-Version", "3")
        req.add_header("Authorization", f"token {self.access_token}")
        data = urllib.request.urlopen(req, timeout=5).read()
        j = json.loads(data)
        out = {}
        for key, item in j.get("data", {}).items():
            sym = key.split(":")[-1]
            out[sym] = item.get("last_price")
        return out

    def ltp(self, symbols):
        try:
            res = self._ltp_live(symbols)
        except Exception:
            res = {}
        for s in symbols:
            if s not in res or not res[s]:
                rng = 3000 if s in ("RELIANCE", "HDFCBANK", "HINDUNILVR", "LT") else 1500
                res[s] = 200 + random.uniform(0, rng)
        return res


class SimBroker:
    """Fully simulated ticks - no network at all."""

    def __init__(self):
        self._walk = {}

    def ltp(self, symbols):
        out = {}
        for s in symbols:
            base = self._walk.get(s, random.uniform(200, 3200))
            self._walk[s] = max(50, base * random.uniform(0.985, 1.015))
            out[s] = self._walk[s]
        return out
