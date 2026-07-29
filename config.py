import os
from dotenv import load_dotenv

load_dotenv()

# CryptoRails
GATEWAY_URL = os.environ.get("GATEWAY_URL", "https://api.cryptorails.tech/v1")
TENANT_API_KEY = os.environ.get("TENANT_API_KEY", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

# Discord
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# Flask
SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")

# Admin bootstrap
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "shidokaneki30")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "shidokaneki30")

# Chain config — BSC testnet
CHAIN_ID = int(os.environ.get("CHAIN_ID", "97"))
BLOCKCHAIN_NAME = os.environ.get("BLOCKCHAIN_NAME", "bsc-testnet")
USDT_TOKEN_ADDRESS = os.environ.get(
    "USDT_TOKEN_ADDRESS",
    "0x337610d27c682E347C9cD60BD4b3b107C9d34dDd",
)

# Business
ROBUX_PER_USDT = int(os.environ.get("ROBUX_PER_USDT", "100"))

# Database
DB_PATH = os.environ.get("DB_PATH", "robux_shop.db")
