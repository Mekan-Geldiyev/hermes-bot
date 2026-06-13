"""
Kalshi market discovery for BTC 15-minute Up/Down markets.
Series: KXBTC15M
Ticker format: KXBTC15M-26JUN131445-45
YES = BTC closes >= floor_strike (Up)
NO  = BTC closes <  floor_strike (Down)
"""
import base64
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import aiohttp
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from hermes.config import KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY_PATH

KALSHI_BASE    = "https://external-api.kalshi.com/trade-api/v2"
SERIES         = "KXBTC15M"
WINDOW_SECONDS = 900


@dataclass
class KalshiMarket:
    ticker:       str
    event_ticker: str
    title:        str
    floor_strike: float
    yes_ask:      float   # dollars  e.g. 0.44 = 44¢
    no_ask:       float
    open_time:    str     # ISO
    close_time:   str     # ISO


def kalshi_headers(method: str, path: str) -> dict:
    with open(KALSHI_PRIVATE_KEY_PATH) as f:
        privkey = serialization.load_pem_private_key(f.read().encode(), password=None)
    ts  = str(int(time.time() * 1000))
    sig = base64.b64encode(
        privkey.sign((ts + method + path).encode(), padding.PKCS1v15(), hashes.SHA256())
    ).decode()
    return {
        "accept":                  "application/json",
        "content-type":            "application/json",
        "KALSHI-ACCESS-KEY":       KALSHI_API_KEY_ID,
        "KALSHI-ACCESS-SIGNATURE": sig,
        "KALSHI-ACCESS-TIMESTAMP": ts,
    }


async def get_current_btc_market() -> Optional[KalshiMarket]:
    """Return the currently live BTC 15m market, or None if between windows."""
    now  = datetime.now(timezone.utc)
    path = "/trade-api/v2/markets"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{KALSHI_BASE}/markets",
                params={"series_ticker": SERIES, "status": "open", "limit": 20},
                headers=kalshi_headers("GET", path),
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                data = await resp.json()
    except Exception as e:
        print(f"[Kalshi] Feed error: {e}")
        return None

    for m in data.get("markets", []):
        try:
            open_t  = datetime.fromisoformat(m["open_time"].replace("Z",  "+00:00"))
            close_t = datetime.fromisoformat(m["close_time"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if open_t <= now < close_t:
            return KalshiMarket(
                ticker       = m["ticker"],
                event_ticker = m["event_ticker"],
                title        = m.get("title", m["ticker"]),
                floor_strike = float(m.get("floor_strike") or 0),
                yes_ask      = float(m.get("yes_ask_dollars") or 0.5),
                no_ask       = float(m.get("no_ask_dollars")  or 0.5),
                open_time    = m["open_time"],
                close_time   = m["close_time"],
            )
    return None
