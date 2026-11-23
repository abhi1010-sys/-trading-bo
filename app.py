from flask import Flask, jsonify, request, render_template

from bot.engine import init_engine, get_engine
from bot.broker import KiteBroker, SimBroker

app = Flask(__name__)


def _broker_from(request):
    if request.args.get("sim") == "1":
        return SimBroker()
    at = request.args.get("kite_token")
    if at:
        return KiteBroker(at)
    return SimBroker()


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
    init_engine(SimBroker())
    app.run(host="127.0.0.1", port=5000, debug=True)
