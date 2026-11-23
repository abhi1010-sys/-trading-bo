from flask import Flask, jsonify, request, render_template

from bot.engine import init_engine, get_engine
from bot.broker import KiteBroker, KiteTickerBroker, SharekhanBroker, SimBroker, YahooBroker

app = Flask(__name__)


def os_get(name):
    import os
    return os.environ.get(name)


def _broker_from(request):
    if request.args.get("sim") == "1":
        return SimBroker()
    at = request.args.get("sk_access_token") or os_get("SHAREKHAN_ACCESS_TOKEN")
    key = request.args.get("sk_api_key") or os_get("SHAREKHAN_API_KEY")
    if key and at:
        return SharekhanBroker(key, at)
    kt = request.args.get("kite_token")
    kkey = request.args.get("kite_api_key")
    if kt and kkey:
        return KiteTickerBroker(kkey, kt)
    if kt:
        return KiteBroker(kt)
    return YahooBroker()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/tick", methods=["POST"])
def tick():
    e = get_engine()
    if e is None:
        return jsonify({"error": "engine not initialised"}), 409
    e.step()
    return jsonify(e.snapshot())


@app.route("/api/status", methods=["GET"])
def status():
    e = get_engine()
    if e is None:
        return jsonify({"running": False, "status": "UNINITIALISED"}), 200
    return jsonify(e.snapshot())


@app.route("/api/start", methods=["POST"])
def start():
    e = init_engine(_broker_from(request))
    e.start()
    return jsonify(e.snapshot())


@app.route("/api/stop", methods=["POST"])
def stop():
    e = get_engine()
    if e is None:
        return jsonify({"running": False, "status": "UNINITIALISED"}), 200
    e.stop()
    return jsonify(e.snapshot())


if __name__ == "__main__":
    import os
    key, token = os.environ.get("SHAREKHAN_API_KEY"), os.environ.get("SHAREKHAN_ACCESS_TOKEN")
    init_engine(SharekhanBroker(key, token) if (key and token) else YahooBroker())
    app.run(host="127.0.0.1", port=5000, debug=True)
