import time
import logging
import requests
from logging.handlers import RotatingFileHandler
from flask import Flask, request, jsonify
from binance.um_futures import UMFutures
from config import *

# ================= 日志 =================
logger = logging.getLogger("binance_bot")
logger.setLevel(logging.INFO)

handler = RotatingFileHandler(
    "./logs/app.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=5
)
formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(message)s"
)
handler.setFormatter(formatter)
logger.addHandler(handler)

# ================= Flask =================
app = Flask(__name__)

# ================= Binance =================
client = UMFutures(
    key=API_KEY,
    secret=API_SECRET,
    base_url=BASE_URL
)

client.change_leverage(symbol=SYMBOL, leverage=LEVERAGE)

logger.info(f"🚀 BOT STARTED | MODE={BINANCE_MODE}")

# ================= Feishu =================
def feishu_notify(msg: str):
    if not FEISHU_WEBHOOK:
        return
    try:
        requests.post(
            FEISHU_WEBHOOK,
            json={"msg_type": "text", "content": {"text": msg}},
            timeout=5
        )
    except Exception as e:
        logger.error(f"Feishu error: {e}")

# ================= Utils =================
def get_balance():
    for b in client.balance():
        if b["asset"] == "USDT":
            return float(b["balance"])
    return 0.0

def get_position_qty():
    p = client.get_position_risk(symbol=SYMBOL)[0]
    return float(p["positionAmt"])

def calc_qty(entry, stop):
    bal = get_balance()
    risk = bal * RISK_PCT
    dist = abs(entry - stop)
    if dist <= 0:
        return 0
    return round(risk / dist, QTY_PRECISION)

def close_if_reverse(side, pos_qty):
    if side == "LONG" and pos_qty < 0:
        _close(abs(pos_qty))
    elif side == "SHORT" and pos_qty > 0:
        _close(abs(pos_qty))

def _close(qty):
    client.new_order(
        symbol=SYMBOL,
        side="BUY" if qty < 0 else "SELL",
        type="MARKET",
        quantity=abs(qty),
        reduceOnly=True
    )
    logger.info(f"Position closed qty={qty}")

# ================= Webhook =================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True, silent=True)
    logger.info(f"Webhook: {data}")

    if not data:
        return jsonify({"error": "invalid json"}), 400

    if data.get("secret") != WEBHOOK_SECRET:
        return jsonify({"error": "unauthorized"}), 403

    side = data.get("side")
    entry = float(data.get("entry", 0))
    stop = float(data.get("stop", 0))

    if side not in ("LONG", "SHORT"):
        return jsonify({"error": "invalid side"}), 400

    qty = calc_qty(entry, stop)
    if qty <= 0:
        return jsonify({"error": "qty too small"}), 400

    pos_qty = get_position_qty()
    close_if_reverse(side, pos_qty)

    if side == "LONG" and pos_qty > 0:
        return jsonify({"status": "skip"})
    if side == "SHORT" and pos_qty < 0:
        return jsonify({"status": "skip"})

    client.new_order(
        symbol=SYMBOL,
        side="BUY" if side == "LONG" else "SELL",
        type="MARKET",
        quantity=qty
    )

    msg = f"✅ {BINANCE_MODE}\n{SYMBOL} {side}\nqty={qty}"
    logger.info(msg)
    feishu_notify(msg)

    return jsonify({"status": "ok"})

# ================= Main =================
if __name__ == "__main__":
    app.run(host=HOST, port=PORT)

