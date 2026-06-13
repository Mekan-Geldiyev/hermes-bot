import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY        = os.getenv("ANTHROPIC_API_KEY")
TELEGRAM_BOT_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID         = os.getenv("TELEGRAM_CHAT_ID")

KALSHI_API_KEY_ID       = os.getenv("KALSHI_API_KEY_ID")
KALSHI_PRIVATE_KEY_PATH = os.getenv("KALSHI_PRIVATE_KEY_PATH")

MAX_TRADE_USDC           = float(os.getenv("MAX_TRADE_USDC", "50"))
MIN_CONFIDENCE           = float(os.getenv("MIN_CONFIDENCE", "0.60"))

# Email alerts
EMAIL_FROM         = os.getenv("EMAIL_FROM", "")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD", "")
EMAIL_TO           = os.getenv("EMAIL_TO", "nightgtwolf@gmail.com")

# Paper trading
PAPER_TRADE              = os.getenv("PAPER_TRADE", "true").lower() == "true"
ACCOUNT_SIZE_USDC        = float(os.getenv("ACCOUNT_SIZE_USDC", "20"))
MAX_POSITION_PCT         = float(os.getenv("MAX_POSITION_PCT", "0.25"))  # max 25% per trade

# Analysis thresholds
MARKOV_PERSISTENCE_THRESHOLD = float(os.getenv("MARKOV_THRESHOLD", "0.55"))
MONTE_CARLO_PATHS            = 500
MONTE_CARLO_STEPS            = 10
TICK_INTERVAL_SECONDS        = 5    # aggregate Binance ticks into N-second bars
TICK_HISTORY                 = 200  # bars kept in Markov buffer
CANDLE_HISTORY               = 50   # 1m candles kept for SMC

# Binance — use binance.us endpoints (binance.com is geo-blocked on US AWS)
BINANCE_WS_URL   = "wss://stream.binance.us:9443/ws/btcusdt@aggTrade"
BINANCE_REST_URL = "https://api.binance.us/api/v3"

# Kalshi
KALSHI_BASE = "https://external-api.kalshi.com/trade-api/v2"
