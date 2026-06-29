"""
Macro trend filter — 12-hour BTC direction from Binance 1h candles.

Compares the last complete 1h close to the close 12 complete hours
prior. Used as a hard veto gate: if the 12h move strongly opposes the
15m signal, the trade is blocked regardless of quant/Claude confidence.
"""
import aiohttp
from dataclasses import dataclass

from hermes.config import BINANCE_REST_URL


@dataclass
class MacroResult:
    trend:        str    # "BULL" | "BEAR" | "NEUTRAL"
    change_pct:   float  # e.g. +1.52 means BTC up 1.52% in 12h
    close_now:    float
    close_12h_ago: float


async def get_macro_trend(neutral_band_pct: float = 0.3) -> MacroResult:
    """
    Fetch last 25 1h candles, compare close_12h_ago to last complete close.
    neutral_band_pct: if |change| < this %, treat as NEUTRAL (no veto).
    """
    url    = f"{BINANCE_REST_URL}/klines"
    params = {"symbol": "BTCUSDT", "interval": "1h", "limit": 25}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=params,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                klines = await resp.json()

        # klines[-1] = current open (incomplete) candle — skip it
        # klines[-2] = last complete 1h close
        # klines[-14] = close 12 complete hours before klines[-2]
        close_now    = float(klines[-2][4])
        close_12h    = float(klines[-14][4])
        change_pct   = (close_now - close_12h) / close_12h * 100

        if change_pct > neutral_band_pct:
            trend = "BULL"
        elif change_pct < -neutral_band_pct:
            trend = "BEAR"
        else:
            trend = "NEUTRAL"

        return MacroResult(
            trend=trend,
            change_pct=round(change_pct, 3),
            close_now=close_now,
            close_12h_ago=close_12h,
        )

    except Exception as e:
        print(f"[Macro] fetch error: {e} — defaulting to NEUTRAL")
        return MacroResult(trend="NEUTRAL", change_pct=0.0, close_now=0.0, close_12h_ago=0.0)
