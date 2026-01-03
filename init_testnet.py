import os
from binance.um_futures import UMFutures
from dotenv import load_dotenv

load_dotenv()

# 使用测试网 API 密钥
API_KEY = os.getenv("BINANCE_TEST_API_KEY")
API_SECRET = os.getenv("BINANCE_TEST_API_SECRET")
BASE_URL = "https://testnet.binancefuture.com"

if not API_KEY or not API_SECRET:
    print("❌ Error: BINANCE_TEST_API_KEY and BINANCE_TEST_API_SECRET must be set in .env file")
    exit(1)

client = UMFutures(
    key=API_KEY,
    secret=API_SECRET,
    base_url=BASE_URL
)

print("🔌 Testing connection...")
try:
    ping_result = client.ping()
    print(f"✅ PING: {ping_result}")
except Exception as e:
    print(f"❌ Connection failed: {e}")
    exit(1)

print("\n📊 Account Info:")
try:
    account = client.account()
    print(f"  Total Wallet Balance: {account.get('totalWalletBalance', 'N/A')} USDT")
    print(f"  Available Balance: {account.get('availableBalance', 'N/A')} USDT")
except Exception as e:
    print(f"❌ Failed to get account info: {e}")
    exit(1)

print("\n💰 Balances:")
try:
    balances = client.balance()
    has_balance = False
    for b in balances:
        balance = float(b["balance"])
        if balance > 0:
            print(f"  {b['asset']}: {balance}")
            has_balance = True
    if not has_balance:
        print("  No balances found")
except Exception as e:
    print(f"❌ Failed to get balances: {e}")

print("\n📈 Positions:")
try:
    positions = client.get_position_risk()
    has_position = False
    for p in positions:
        pos_amt = float(p["positionAmt"])
        if pos_amt != 0:
            print(f"  {p['symbol']}: {pos_amt} (Entry: {p.get('entryPrice', 'N/A')})")
            has_position = True
    if not has_position:
        print("  No open positions")
except Exception as e:
    print(f"❌ Failed to get positions: {e}")

print("\n✅ Testnet connection successful!")

