from datetime import datetime, time, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


def now_ist():
    return datetime.now(IST)


def is_market_open():
    n = now_ist()
    if n.weekday() >= 5:
        return False
    return MARKET_OPEN <= n.time() < MARKET_CLOSE
