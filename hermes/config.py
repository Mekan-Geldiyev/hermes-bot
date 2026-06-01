import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY        = os.getenv("ANTHROPIC_API_KEY")
TELEGRAM_BOT_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID         = os.getenv("TELEGRAM_CHAT_ID")

POLYMARKET_PRIVATE_KEY   = os.getenv("POLYMARKET_PRIVATE_KEY")
POLYMARKET_API_KEY       = os.getenv("POLYMARKET_API_KEY")
POLYMARKET_API_SECRET    = os.getenv("POLYMARKET_API_SECRET")
POLYMARKET_API_PASSPHRASE = os.getenv("POLYMARKET_API_PASSPHRASE")

MAX_TRADE_USDC           = float(os.getenv("MAX_TRADE_USDC", "50"))
MIN_CONFIDENCE           = float(os.getenv("MIN_CONFIDENCE", "0.65"))

# Paper trading
PAPER_TRADE              = os.getenv("PAPER_TRADE", "true").lower() == "true"
ACCOUNT_SIZE_USDC        = float(os.getenv("ACCOUNT_SIZE_USDC", "20"))
MAX_POSITION_PCT         = float(os.getenv("MAX_POSITION_PCT", "0.25"))  # max 25% per trade

# Analysis thresholds
MARKOV_PERSISTENCE_THRESHOLD = float(os.getenv("MARKOV_THRESHOLD", "0.62"))
MONTE_CARLO_PATHS            = 500
MONTE_CARLO_STEPS            = 10
TICK_INTERVAL_SECONDS        = 5    # aggregate Binance ticks into N-second bars
TICK_HISTORY                 = 200  # bars kept in Markov buffer
CANDLE_HISTORY               = 50   # 1m candles kept for SMC

# Binance — use binance.us endpoints (binance.com is geo-blocked on US AWS)
BINANCE_WS_URL   = "wss://stream.binance.us:9443/ws/btcusdt@aggTrade"
BINANCE_REST_URL = "https://api.binance.us/api/v3"

# Polymarket
CLOB_HOST    = "https://clob.polymarket.com"
GAMMA_HOST   = "https://gamma-api.polymarket.com"
POLYGON_CHAIN_ID = 137
