import os
import json
import time
import logging
import requests
from datetime import datetime
from typing import Dict, Optional, Tuple, Any, Union
from logging.handlers import RotatingFileHandler
from flask import Flask, request, jsonify, render_template_string
from binance.um_futures import UMFutures
from binance.client import Client
from binance.error import ClientError, ServerError
from dotenv import load_dotenv

load_dotenv()

# ================= 配置加载 =================
# ========== MODE ==========
BINANCE_MODE = os.getenv("BINANCE_MODE", "testnet").lower()
if BINANCE_MODE not in ("testnet", "main"):
    raise RuntimeError("BINANCE_MODE must be testnet or main")

# ========== TRADE TYPE ==========
TRADE_TYPE = os.getenv("TRADE_TYPE", "futures").lower()
if TRADE_TYPE not in ("futures", "spot"):
    raise RuntimeError("TRADE_TYPE must be futures or spot")

# ========== API KEY ==========
if BINANCE_MODE == "testnet":
    API_KEY = os.getenv("BINANCE_TEST_API_KEY")
    API_SECRET = os.getenv("BINANCE_TEST_API_SECRET")
    if TRADE_TYPE == "futures":
        BASE_URL = "https://testnet.binancefuture.com"
    else:
        BASE_URL = "https://testnet.binance.vision"
else:
    API_KEY = os.getenv("BINANCE_MAIN_API_KEY")
    API_SECRET = os.getenv("BINANCE_MAIN_API_SECRET")
    if TRADE_TYPE == "futures":
        BASE_URL = "https://fapi.binance.com"
    else:
        BASE_URL = None  # 现货使用默认 URL

# ========== Trading ==========
SYMBOL = "BTCUSDT"
LEVERAGE = int(os.getenv("LEVERAGE", 3)) if TRADE_TYPE == "futures" else 1
RISK_PCT = float(os.getenv("RISK_PCT", 0.01))
QTY_PRECISION = int(os.getenv("QTY_PRECISION", 3))
SKIP_LEVERAGE_SETUP = os.getenv("SKIP_LEVERAGE_SETUP", "false").lower() == "true"

# ========== 交易历史文件 ==========
TRADE_HISTORY_FILE = "./logs/trade_history.json"

# ========== Security ==========
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

# ========== Feishu ==========
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")

# ========== Flask ==========
HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", 80))

# ========== 配置验证 ==========
missing = []
for k, v in {
    "API_KEY": API_KEY,
    "API_SECRET": API_SECRET,
}.items():
    if not v:
        missing.append(k)

if missing:
    raise RuntimeError(f"Missing ENV vars: {missing}")

# 验证配置合理性
if RISK_PCT <= 0 or RISK_PCT > 1:
    raise RuntimeError(f"RISK_PCT must be between 0 and 1, got {RISK_PCT}")

if TRADE_TYPE == "futures" and (LEVERAGE < 1 or LEVERAGE > 125):
    raise RuntimeError(f"LEVERAGE must be between 1 and 125, got {LEVERAGE}")

if QTY_PRECISION < 0 or QTY_PRECISION > 8:
    raise RuntimeError(f"QTY_PRECISION must be between 0 and 8, got {QTY_PRECISION}")

# ================= 日志初始化 =================
logger = logging.getLogger("binance_bot")
logger.setLevel(logging.INFO)

# 确保日志目录存在
os.makedirs("./logs", exist_ok=True)

handler = RotatingFileHandler(
    "./logs/app.log",
    maxBytes=50 * 1024 * 1024,
    backupCount=5
)
formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"  # 添加这个参数，指定时间格式
)
handler.setFormatter(formatter)
logger.addHandler(handler)

# 同时输出到控制台
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# ================= Flask =================
app = Flask(__name__)

# ================= Binance 客户端初始化 =================
if TRADE_TYPE == "futures":
    client: Union[UMFutures, Client] = UMFutures(
        key=API_KEY,
        secret=API_SECRET,
        base_url=BASE_URL
    )
else:
    # 现货交易
    client = Client(
        api_key=API_KEY,
        api_secret=API_SECRET,
        testnet=(BINANCE_MODE == "testnet")
    )
    if BINANCE_MODE == "testnet":
        client.API_URL = "https://testnet.binance.vision/api"

def test_api_connection_with_retry(max_retries: int = 3) -> bool:
    """
    测试 API 连接，带重试机制
    
    Args:
        max_retries: 最大重试次数
        
    Returns:
        连接是否成功
    """
    for attempt in range(max_retries):
        try:
            # 使用 ping() 而不是 account()，更轻量且不会触发速率限制
            client.ping()
            logger.info(f"✅ API connection successful | Mode: {BINANCE_MODE}")
            return True
        except ClientError as e:
            logger.error(f"❌ API connection failed (ClientError): {e}")
            logger.error("❌ Please check your API_KEY, API_SECRET, and IP whitelist settings")
            raise
        except ServerError as e:
            logger.error(f"❌ API connection failed (ServerError): {e}")
            logger.error("❌ Binance server error, please try again later")
            raise
        except Exception as e:
            logger.error(f"❌ API connection failed (Unknown): {e}")
            raise
    
    return False

# 测试 API 连接（带重试）
test_api_connection_with_retry()

# 尝试设置杠杆（仅期货，如果未跳过）
if TRADE_TYPE == "futures" and not SKIP_LEVERAGE_SETUP:
    time.sleep(1)  # 等待 1 秒，避免连续请求
    try:
        client.change_leverage(symbol=SYMBOL, leverage=LEVERAGE)
        logger.info(f"✅ Leverage set to {LEVERAGE}x for {SYMBOL}")
    except ClientError as e:
        # 检查是否是权限错误（401）
        if e.status_code == 401 or (hasattr(e, 'error_code') and e.error_code == -2015):
            logger.warning(f"⚠️ Failed to set leverage: API key lacks permission (401)")
            logger.warning("⚠️ This is usually because:")
            logger.warning("   1. API key doesn't have 'Enable Futures' permission")
            logger.warning("   2. IP address is not whitelisted")
            logger.warning("   3. Leverage may already be set correctly")
            logger.warning("⚠️ Application will continue, leverage may need to be set manually")
        else:
            logger.warning(f"⚠️ Failed to set leverage (ClientError): {e}")
    except ServerError as e:
        logger.warning(f"⚠️ Failed to set leverage (ServerError): {e}")
    except Exception as e:
        logger.warning(f"⚠️ Failed to set leverage (Unknown): {e}")
    else:
        logger.info(f"⏭️ Skipping leverage setup (SKIP_LEVERAGE_SETUP=true)")
elif TRADE_TYPE == "spot":
    logger.info(f"ℹ️ Spot trading mode: leverage not applicable")

logger.info(f"🚀 BOT STARTED | MODE={BINANCE_MODE} | TYPE={TRADE_TYPE} | SYMBOL={SYMBOL} | LEVERAGE={LEVERAGE}x")

# ================= Feishu =================
def feishu_notify(msg: str) -> None:
    """
    发送飞书通知
    
    Args:
        msg: 要发送的消息内容
    """
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

# ================= 交易历史记录 =================
def save_trade_history(side: str, qty: float, entry: float, stop: float, order_id: Optional[int] = None, symbol: Optional[str] = None, message: Optional[str] = None) -> None:
    """
    保存交易记录到文件
    
    Args:
        side: 交易方向 (LONG/SHORT)
        qty: 交易数量
        entry: 入场价格
        stop: 止损价格
        order_id: 订单ID（可选）
        symbol: 交易标的（可选，默认使用 SYMBOL）
        message: 交易消息/备注（可选）
    """
    try:
        trade_record = {
            "timestamp": datetime.now().isoformat(),
            "side": side,
            "qty": qty,
            "entry": entry,
            "stop": stop,
            "order_id": order_id,
            "symbol": symbol or SYMBOL,
            "mode": BINANCE_MODE
        }
        
        # 如果提供了消息，添加到记录中
        if message:
            trade_record["message"] = message
        
        # 读取现有历史记录
        history = []
        if os.path.exists(TRADE_HISTORY_FILE):
            try:
                with open(TRADE_HISTORY_FILE, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read trade history: {e}")
        
        # 添加新记录
        history.append(trade_record)
        
        # 只保留最近1000条记录
        if len(history) > 1000:
            history = history[-1000:]
        
        # 保存到文件
        os.makedirs(os.path.dirname(TRADE_HISTORY_FILE), exist_ok=True)
        with open(TRADE_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Trade history saved: {trade_record}")
    except Exception as e:
        logger.error(f"Failed to save trade history: {e}")

def get_trade_history(limit: int = 50) -> list:
    """
    获取交易历史记录
    
    Args:
        limit: 返回的记录数量限制
        
    Returns:
        交易历史记录列表
    """
    try:
        if not os.path.exists(TRADE_HISTORY_FILE):
            return []
        
        with open(TRADE_HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
        
        # 返回最近的记录
        return history[-limit:] if limit > 0 else history
    except Exception as e:
        logger.error(f"Failed to get trade history: {e}")
        return []

# ================= Utils =================
def get_balance() -> float:
    """
    获取 USDT 余额
    
    Returns:
        USDT 余额，如果获取失败则抛出异常
    """
    try:
        if TRADE_TYPE == "futures":
            balances = client.balance()
            for b in balances:
                if b["asset"] == "USDT":
                    return float(b["balance"])
        else:
            # 现货交易
            account = client.get_account()
            for b in account["balances"]:
                if b["asset"] == "USDT":
                    return float(b["free"])
        logger.warning("USDT balance not found")
        return 0.0
    except ClientError as e:
        logger.error(f"Failed to get balance (ClientError): {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to get balance (Unknown): {e}")
        raise

def get_position_qty() -> float:
    """
    获取当前持仓数量
    
    Returns:
        持仓数量，正数表示多仓（或现货持仓），负数表示空仓，0 表示无持仓
    """
    try:
        if TRADE_TYPE == "futures":
            positions = client.get_position_risk(symbol=SYMBOL)
            if not positions:
                return 0.0
            return float(positions[0]["positionAmt"])
        else:
            # 现货交易：查询持有的币种数量
            account = client.get_account()
            base_asset = SYMBOL.replace("USDT", "")  # 例如 BTCUSDT -> BTC
            for b in account["balances"]:
                if b["asset"] == base_asset:
                    qty = float(b["free"])
                    # 现货只有多仓（持有），返回正数表示持有数量
                    return qty if qty > 0 else 0.0
            return 0.0
    except ClientError as e:
        logger.error(f"Failed to get position (ClientError): {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to get position (Unknown): {e}")
        raise

def calc_qty(entry: float, stop: float) -> float:
    """
    根据入场价和止损价计算交易数量
    
    Args:
        entry: 入场价格
        stop: 止损价格
        
    Returns:
        计算出的交易数量，如果计算失败返回 0
    """
    if entry <= 0 or stop <= 0:
        logger.error(f"Invalid entry/stop: entry={entry}, stop={stop}")
        return 0.0
    
    dist = abs(entry - stop)
    if dist <= 0:
        logger.error(f"Entry and stop are too close: entry={entry}, stop={stop}")
        return 0.0
    
    try:
        bal = get_balance()
        if bal <= 0:
            logger.error(f"Insufficient balance: {bal}")
            return 0.0
        
        risk = bal * RISK_PCT
        qty = round(risk / dist, QTY_PRECISION)
        logger.info(f"Calculated qty: balance={bal}, risk={risk}, dist={dist}, qty={qty}")
        return qty
    except Exception as e:
        logger.error(f"Failed to calculate qty: {e}")
        return 0.0

def close_if_reverse(side: str, pos_qty: float) -> None:
    """
    如果当前持仓方向与交易方向相反，先平仓
    
    Args:
        side: 交易方向 (LONG/SHORT)
        pos_qty: 当前持仓数量
    """
    if TRADE_TYPE == "futures":
        # 期货：处理反向持仓
        if side == "LONG" and pos_qty < 0:
            logger.info(f"Closing reverse position: side={side}, pos_qty={pos_qty}")
            _close(abs(pos_qty))
        elif side == "SHORT" and pos_qty > 0:
            logger.info(f"Closing reverse position: side={side}, pos_qty={pos_qty}")
            _close(abs(pos_qty))
    else:
        # 现货：如果要做空但持有现货，需要先卖出
        # 如果要做多但持有现货，可以继续持有或先卖出再买入
        if side == "SHORT" and pos_qty > 0:
            logger.info(f"Closing spot position before SHORT: pos_qty={pos_qty}")
            _close(pos_qty)
        # 现货做多时，如果已有持仓，可以选择加仓或跳过

def _close(qty: float) -> None:
    """
    执行平仓操作
    
    Args:
        qty: 要平仓的数量（正数）
    """
    if qty <= 0:
        logger.warning(f"Invalid close qty: {qty}")
        return
    
    try:
        if TRADE_TYPE == "futures":
            side = "BUY" if qty < 0 else "SELL"
            result = client.new_order(
                symbol=SYMBOL,
                side=side,
                type="MARKET",
                quantity=abs(qty),
                reduceOnly=True
            )
        else:
            # 现货：卖出持有的币种
            result = client.order_market_sell(
                symbol=SYMBOL,
                quantity=qty
            )
        logger.info(f"Position closed: qty={qty}, order_id={result.get('orderId')}")
    except ClientError as e:
        logger.error(f"Failed to close position (ClientError): {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to close position (Unknown): {e}")
        raise

# ================= Webhook =================
@app.route("/webhook", methods=["POST"])
def webhook() -> Tuple[Dict[str, Any], int]:
    """
    统一 webhook 入口，通过 type 区分处理逻辑
    type=cn: A 股信号，仅记录历史和飞书通知
    type=crypto: 币安交易信号，执行下单逻辑
    
    Returns:
        JSON 响应和 HTTP 状态码
    """
    try:
        # 尝试多种方式获取 JSON 数据
        data = None
        
        # 方法1: 尝试从 JSON 请求体获取
        data = request.get_json(force=True, silent=True)
        
        # 方法2: 如果失败，尝试从原始数据获取（TradingView 可能发送纯文本 JSON）
        if not data:
            raw_data = request.get_data(as_text=True)
            logger.info(f"Raw webhook data: {raw_data[:200]}")  # 记录前200字符用于调试
            
            if raw_data:
                try:
                    # 尝试解析 JSON 字符串
                    data = json.loads(raw_data)
                    logger.info("Successfully parsed JSON from raw data")
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON from raw data: {e}")
                    # 方法3: 尝试从表单数据获取
                    if request.form:
                        data = dict(request.form)
                        logger.info("Using form data")
        
        # 验证 JSON
        if not data:
            logger.warning("Invalid JSON in webhook request")
            logger.warning(f"Content-Type: {request.content_type}")
            logger.warning(f"Raw data: {request.get_data(as_text=True)[:500]}")
            return jsonify({"error": "invalid json"}), 400

        # 识别类型（默认 crypto）
        req_type = str(data.get("type", "crypto")).lower()
        if req_type not in ("cn", "crypto"):
            logger.warning(f"Invalid webhook type: {req_type}")
            return jsonify({"error": "invalid type, must be cn or crypto"}), 400

        # ================= A股逻辑 =================
        if req_type == "cn":
            # 验证 action（只处理 ENTRY，忽略 EXIT）
            action = data.get("action", "ENTRY").upper()
            if action != "ENTRY":
                logger.info(f"Ignoring non-ENTRY action: {action}")
                return jsonify({"status": "ignored", "reason": f"action {action} not processed"}), 200

            # 验证和解析参数
            side = data.get("side", "").upper()
            if side != "LONG":
                logger.warning(f"Stock webhook only supports LONG, got: {side}")
                return jsonify({"error": "only LONG orders are supported"}), 400

            # 获取交易参数
            symbol = data.get("symbol", "")
            try:
                qty = float(data.get("qty", 0))
                entry = float(data.get("entry", 0))
                stop = float(data.get("stop", 0))
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid qty/entry/stop values: {e}")
                return jsonify({"error": "invalid qty, entry or stop value"}), 400

            # 验证价格参数
            if entry <= 0 or stop <= 0 or qty <= 0:
                logger.warning(f"Invalid values: qty={qty}, entry={entry}, stop={stop}")
                return jsonify({"error": "qty, entry and stop must be positive"}), 400

            # 获取可选参数
            tp1 = data.get("tp1")
            tp2 = data.get("tp2")
            score = data.get("score")
            
            # 发送飞书通知
            msg_parts = [
                "📈 A股交易信号",
                f"标的: {symbol}",
                f"方向: {side}",
                f"数量: {qty}",
                f"入场: {entry}",
                f"止损: {stop}"
            ]
            if tp1:
                msg_parts.append(f"止盈1: {tp1}")
            if tp2:
                msg_parts.append(f"止盈2: {tp2}")
            if score:
                msg_parts.append(f"评分: {score}")
            
            msg = "\n".join(msg_parts)
            logger.info(f"Stock trade signal: {msg}")
            feishu_notify(msg)

            # 保存交易历史
            save_trade_history(
                side=side,
                qty=qty,
                entry=entry,
                stop=stop,
                order_id=None,
                symbol=symbol,
                message=msg
            )

            return jsonify({
                "status": "ok",
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "entry": entry,
                "stop": stop,
                "message": "Trade signal recorded"
            }), 200

        # ================= 币安交易逻辑 =================
        # 验证和解析参数
        side = data.get("side", "").upper()
        if side not in ("LONG", "SHORT"):
            logger.warning(f"Invalid side: {side}")
            return jsonify({"error": "invalid side, must be LONG or SHORT"}), 400

        try:
            entry = float(data.get("entry", 0))
            stop = float(data.get("stop", 0))
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid entry/stop values: {e}")
            return jsonify({"error": "invalid entry or stop value"}), 400

        # 验证价格参数
        if entry <= 0 or stop <= 0:
            logger.warning(f"Invalid price values: entry={entry}, stop={stop}")
            return jsonify({"error": "entry and stop must be positive"}), 400

        if abs(entry - stop) <= 0:
            logger.warning(f"Entry and stop are too close: entry={entry}, stop={stop}")
            return jsonify({"error": "entry and stop must be different"}), 400

        # 计算交易数量
        qty = calc_qty(entry, stop)
        if qty <= 0:
            logger.warning(f"Calculated qty too small: qty={qty}, entry={entry}, stop={stop}")
            return jsonify({"error": "qty too small, check balance and risk settings"}), 400

        # 获取当前持仓
        try:
            pos_qty = get_position_qty()
        except Exception as e:
            logger.error(f"Failed to get position: {e}")
            return jsonify({"error": "failed to get position"}), 500

        # 如果方向相反，先平仓
        try:
            close_if_reverse(side, pos_qty)
        except Exception as e:
            logger.error(f"Failed to close reverse position: {e}")
            return jsonify({"error": "failed to close reverse position"}), 500

        # 检查是否已有同向持仓
        if TRADE_TYPE == "futures":
            if side == "LONG" and pos_qty > 0:
                logger.info(f"Skipping: already have LONG position, qty={pos_qty}")
                return jsonify({"status": "skip", "reason": "already have LONG position"})
            if side == "SHORT" and pos_qty < 0:
                logger.info(f"Skipping: already have SHORT position, qty={pos_qty}")
                return jsonify({"status": "skip", "reason": "already have SHORT position"})
        else:
            # 现货：不支持做空
            if side == "SHORT":
                logger.warning("SHORT orders not supported in spot trading")
                return jsonify({"error": "SHORT orders not supported in spot trading"}), 400
            # 现货做多时，如果已有持仓可以选择加仓或跳过
            if side == "LONG" and pos_qty > 0:
                logger.info(f"Already have spot position, will add to position: current_qty={pos_qty}")

        # 执行交易
        try:
            if TRADE_TYPE == "futures":
                order_side = "BUY" if side == "LONG" else "SELL"
                result = client.new_order(
                    symbol=SYMBOL,
                    side=order_side,
                    type="MARKET",
                    quantity=qty
                )
            else:
                # 现货：只支持买入，使用市价单
                if side == "LONG":
                    # 现货买入：使用 quoteOrderQty（USDT 金额）或 quantity（币数量）
                    # 这里使用 USDT 金额更准确
                    usdt_amount = qty * entry
                    result = client.order_market_buy(
                        symbol=SYMBOL,
                        quoteOrderQty=round(usdt_amount, 2)  # USDT 金额，保留2位小数
                    )
                else:
                    raise ValueError("SHORT orders not supported in spot trading")
            
            order_id = result.get("orderId")
            logger.info(f"Order placed: {result}")
            
            # 保存交易历史
            save_trade_history(side, qty, entry, stop, order_id)
        except ClientError as e:
            logger.error(f"Failed to place order (ClientError): {e}")
            return jsonify({"error": f"order failed: {e}"}), 500
        except Exception as e:
            logger.error(f"Failed to place order (Unknown): {e}")
            return jsonify({"error": "order failed"}), 500

        # 发送通知
        msg = f"✅ {BINANCE_MODE}\n{SYMBOL} {side}\nqty={qty}\nentry={entry}\nstop={stop}"
        logger.info(msg)
        feishu_notify(msg)

        return jsonify({"status": "ok", "qty": qty, "side": side, "order_id": order_id})

    except Exception as e:
        logger.error(f"Unexpected error in webhook: {e}", exc_info=True)
        return jsonify({"error": "internal server error"}), 500

# ================= Health Check =================
@app.route("/health", methods=["GET"])
def health() -> Tuple[Dict[str, Any], int]:
    """
    健康检查端点
    
    Returns:
        JSON 响应和状态码
    """
    try:
        # 测试 API 连接
        client.ping()
        return jsonify({
            "status": "healthy",
            "mode": BINANCE_MODE,
            "trade_type": TRADE_TYPE,
            "symbol": SYMBOL
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 503

# ================= Status Endpoint =================
@app.route("/status", methods=["GET"])
def status() -> Tuple[Dict[str, Any], int]:
    """
    获取机器人状态信息（余额、持仓、配置）
    
    Returns:
        JSON 响应包含余额、持仓、配置等信息
    """
    try:
        # 获取账户信息
        if TRADE_TYPE == "futures":
            account_info = client.account()
        else:
            account_info = client.get_account()
        
        # 获取余额
        balance = 0.0
        try:
            balance = get_balance()
        except Exception as e:
            logger.warning(f"Failed to get balance in status: {e}")
        
        # 获取持仓
        position_qty = 0.0
        position_info = None
        try:
            position_qty = get_position_qty()
            if TRADE_TYPE == "futures":
                positions = client.get_position_risk(symbol=SYMBOL)
                if positions:
                    pos = positions[0]
                    position_info = {
                        "quantity": float(pos.get("positionAmt", 0)),
                        "entry_price": float(pos.get("entryPrice", 0)) if pos.get("entryPrice") else None,
                        "mark_price": float(pos.get("markPrice", 0)) if pos.get("markPrice") else None,
                        "unrealized_pnl": float(pos.get("unRealizedProfit", 0)) if pos.get("unRealizedProfit") else None,
                        "leverage": int(pos.get("leverage", LEVERAGE))
                    }
            else:
                # 现货：显示持有的币种数量
                base_asset = SYMBOL.replace("USDT", "")
                if position_qty > 0:
                    # 获取当前价格来计算价值
                    try:
                        ticker = client.get_symbol_ticker(symbol=SYMBOL)
                        current_price = float(ticker.get("price", 0))
                        value_usdt = position_qty * current_price if current_price > 0 else None
                    except:
                        value_usdt = None
                    position_info = {
                        "quantity": position_qty,
                        "asset": base_asset,
                        "value_usdt": value_usdt
                    }
        except Exception as e:
            logger.warning(f"Failed to get position in status: {e}")
        
        # 获取最近交易历史
        trade_history = get_trade_history(limit=10)
        
        response_data = {
            "status": "ok",
            "mode": BINANCE_MODE,
            "trade_type": TRADE_TYPE,
            "symbol": SYMBOL,
            "balance": {
                "usdt": balance
            },
            "position": {
                "quantity": position_qty,
                "side": "LONG" if position_qty > 0 else "SHORT" if position_qty < 0 else "NONE",
                "details": position_info
            },
            "config": {
                "leverage": LEVERAGE if TRADE_TYPE == "futures" else 1,
                "risk_pct": RISK_PCT,
                "qty_precision": QTY_PRECISION
            },
            "recent_trades": trade_history,
            "trade_history_count": len(get_trade_history(limit=0))
        }
        
        # 添加期货特有的余额信息
        if TRADE_TYPE == "futures":
            response_data["balance"]["total_wallet_balance"] = float(account_info.get("totalWalletBalance", 0))
            response_data["balance"]["available_balance"] = float(account_info.get("availableBalance", 0))
        else:
            # 现货：显示总资产
            response_data["balance"]["available"] = balance
        
        return jsonify(response_data), 200
    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

# ================= Main =================
if __name__ == "__main__":
    logger.info(f"Starting Flask server on {HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=False)

