import os
from dotenv import load_dotenv

load_dotenv()

# ========== MODE ==========
BINANCE_MODE = os.getenv("BINANCE_MODE", "testnet").lower()
if BINANCE_MODE not in ("testnet", "main"):
    raise RuntimeError("BINANCE_MODE must be testnet or main")

# ========== API KEY ==========
if BINANCE_MODE == "testnet":
    API_KEY = os.getenv("BINANCE_TEST_API_KEY")
    API_SECRET = os.getenv("BINANCE_TEST_API_SECRET")
    BASE_URL = "https://testnet.binancefuture.com"
else:
    API_KEY = os.getenv("BINANCE_MAIN_API_KEY")
    API_SECRET = os.getenv("BINANCE_MAIN_API_SECRET")
    BASE_URL = None  # mainnet 默认

# ========== Trading ==========
SYMBOL = "BTCUSDT"
LEVERAGE = 3
RISK_PCT = 0.01
QTY_PRECISION = 3

# ========== Security ==========
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

# ========== Feishu ==========
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")

# ========== Flask ==========
HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", 80))

# ========== Check ==========
missing = []
for k, v in {
    "API_KEY": API_KEY,
    "API_SECRET": API_SECRET,
    "WEBHOOK_SECRET": WEBHOOK_SECRET,
}.items():
    if not v:
        missing.append(k)

if missing:
    raise RuntimeError(f"Missing ENV vars: {missing}")

