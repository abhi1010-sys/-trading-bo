#!/usr/bin/env python
"""One-time (and daily) Kite Connect login helper.

Zero-delay ticks need a Kite Connect app (https://developers.kite.trade,
paid subscription) and a fresh access token every morning before market
hours. This helper prints the login URL, exchanges your request_token for
an access_token, and tells you how to start the app with it.

Usage:
    export KITE_API_KEY=xxxx KITE_API_SECRET=yyyy
    python scripts/kite_login.py
"""
import os

from kiteconnect import KiteConnect


def main():
    api_key = os.environ.get("KITE_API_KEY")
    api_secret = os.environ.get("KITE_API_SECRET")
    if not (api_key and api_secret):
        raise SystemExit("set KITE_API_KEY and KITE_API_SECRET first (see scripts header)")

    kite = KiteConnect(api_key=api_key)
    print("1. Open this URL in a browser and log in with your Zerodha credentials:")
    print()
    print("   " + kite.login_url())
    print()
    request_token = input("2. Paste the request_token from the redirect URL: ").strip()
    session = kite.generate_session(request_token, api_secret=api_secret)
    print()
    print("3. Start the zero-delay bot:")
    print()
    print(f"   KITE_API_KEY={api_key} KITE_ACCESS_TOKEN={session['access_token']} python app.py")
    print()
    print("Note: access tokens expire daily - repeat this before each session.")


if __name__ == "__main__":
    main()
