#!/usr/bin/env python
"""Daily (per-session) Sharekhan login helper.

Requirements: a Sharekhan Trading API key + secret (free with your
account at https://www.sharekhan.com/trading-api). Access tokens are
per-session - repeat before each market day.

Usage:
    export SHAREKHAN_API_KEY=xxxx SHAREKHAN_SECRET_KEY=yyyy
    python scripts/sharekhan_login.py
"""
import os

from SharekhanApi.sharekhanConnect import SharekhanConnect


def main():
    api_key = os.environ.get("SHAREKHAN_API_KEY")
    secret = os.environ.get("SHAREKHAN_SECRET_KEY")
    if not (api_key and secret):
        raise SystemExit("set SHAREKHAN_API_KEY and SHAREKHAN_SECRET_KEY first (see header)")

    login = SharekhanConnect(api_key)
    print("1. Open this URL in a browser and log in with your Sharekhan credentials:")
    print()
    print("   " + login.login_url())
    print()
    request_token = input("2. Paste the request_token from the redirect URL: ").strip()
    session = login.generate_session(request_token, secret)
    print()
    print("session response:", session)
    print()
    print("3. Get the access token (if needed):")
    print("   access_token = login.get_access_token(api_key, session, state)")
    print()
    print("4. Start the zero-delay bot:")
    print()
    print(f"   SHAREKHAN_API_KEY={api_key} SHAREKHAN_ACCESS_TOKEN=<token> python app.py")
    print()
    print("Repeat this flow before each market day - tokens are per-session.")


if __name__ == "__main__":
    main()
