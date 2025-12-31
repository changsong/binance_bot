import os
from binance.client import Client
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")

client = Client(API_KEY, API_SECRET, testnet=True)
client.API_URL = "https://testnet.binance.vision/api"

print("🔌 PING:", client.ping())

account = client.get_account()
print("\n💰 Balances:")
for b in account["balances"]:
    if float(b["free"]) > 0:
        print(f"{b['asset']}: {b['free']}")

