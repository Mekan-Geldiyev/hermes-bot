import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY        = os.getenv("ANTHROPIC_API_KEY")
TELEGRAM_BOT_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID         = os.getenv("TELEGRAM_CHAT_ID")

KALSHI_API_KEY_ID       = os.getenv("KALSHI_API_KEY_ID")
KALSHI_PRIVATE_KEY_PATH = os.getenv("KALSHI_PRIVATE_KEY_PATH")

MAX_TRADE_USDC           = float(os.getenv("MAX_TRADE_USDC", "50"))

# Trade log audit (32 trades): confidence 0.60-0.65 band had a 64.0% win rate
# (+$31.76 net); confidence >=0.70 had only 28.6% (-$21.12 net) despite Claude
# predicting higher. Hard gate: only trade inside the validated band. Anything
# outside it is logged for observation only (see hermes/signal_log.py),
# never traded. Tune via .env without a code change.
MIN_TRADE_CONFIDENCE = float(os.getenv("MIN_TRADE_CONFIDENCE", "0.63"))
MAX_TRADE_CONFIDENCE = float(os.getenv("MAX_TRADE_CONFIDENCE", "0.68"))

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
