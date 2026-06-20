"""
Paper trading ledger for Hermes.

Win/loss is determined by Kalshi's actual resolution (result field on the market).
Kalshi uses CF Benchmarks BRTI as the price oracle.

P&L maths (prediction market binary):
  - You spend $size buying shares at price p (e.g. YES at 0.44)
  - Shares bought = size / p
  - WIN: receive $1 per share → pnl = (size/p) - size
  - LOSE: lose your stake    → pnl = -size
"""
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiohttp

from hermes.config import ACCOUNT_SIZE_USDC, MAX_POSITION_PCT

LEDGER_PATH = os.path.join(os.path.dirname(__file__), "paper_trades.json")


# ─── ledger I/O ───────────────────────────────────────────────────────────────

def _load() -> dict:
    if not os.path.exists(LEDGER_PATH):
        return {"initial": ACCOUNT_SIZE_USDC, "balance": ACCOUNT_SIZE_USDC, "trades": []}
    with open(LEDGER_PATH) as f:
        return json.load(f)


def _save(ledger: dict) -> None:
    with open(LEDGER_PATH, "w") as f:
        json.dump(ledger, f, indent=2)


def get_balance() -> float:
    return _load()["balance"]


# ─── sizing ───────────────────────────────────────────────────────────────────

SIZING_CONFIDENCE_CAP = 0.65  # confidence above this is poorly calibrated for sizing — see trade log audit


def kelly_size(confidence: float, price: float, balance: float) -> float:
    confidence = min(confidence, SIZING_CONFIDENCE_CAP)
    if price <= 0.0 or price >= 1.0 or confidence <= price:
        return 0.0
    b = (1.0 - price) / price
    kelly_f = (b * confidence - (1.0 - confidence)) / b
    if kelly_f <= 0.0:
        return 0.0
    return round(min(kelly_f * 0.5 * balance, balance * MAX_POSITION_PCT), 2)


# ─── record ───────────────────────────────────────────────────────────────────

def record_trade(
    market_title: str,
    close_time: str,
    ticker: str,
    direction: str,
    entry_btc_price: float,
    yes_ask: float,
    no_ask: float,
    confidence: float,
    reasoning: str,
    size_override: Optional[float] = None,
) -> Optional[dict]:
    ledger  = _load()
    balance = ledger["balance"]
    price   = yes_ask if direction == "BULL" else no_ask
    size    = size_override if size_override is not None else kelly_size(confidence, price, balance)

    if size < 0.05:
        print(f"[Paper] Size ${size:.2f} too small, skip")
        return None

    trade = {
        "id":         datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "market":     market_title,
        "close_time": close_time,
        "ticker":     ticker,
        "direction":  direction,
        "entry_btc":  round(entry_btc_price, 2),
        "yes_price":  yes_ask,
        "no_price":   no_ask,
        "confidence": round(confidence, 4),
        "reasoning":  reasoning,
        "size_usdc":  size,
        "result":     None,
        "exit_btc":   None,
        "pnl":        None,
    }

    ledger["trades"].append(trade)
    _save(ledger)

    print(
        f"[Paper] 📋 LOGGED {direction} | size=${size:.2f} | "
        f"odds={price:.3f} | conf={confidence:.0%} | "
        f"balance=${balance:.2f} | market: {market_title}"
    )
    return trade


# ─── resolution via Kalshi ────────────────────────────────────────────────────

async def _kalshi_outcome(ticker: str) -> Optional[bool]:
    """
    Returns True (YES/Up won), False (NO/Down won), or None (not resolved yet).
    Queries the market's result field directly from Kalshi.
    """
    if not ticker:
        return None
    try:
        from hermes.feeds.kalshi_feed import kalshi_headers, KALSHI_BASE
        path = f"/trade-api/v2/markets/{ticker}"
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{KALSHI_BASE}/markets/{ticker}",
                headers=kalshi_headers("GET", path),
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                data = await resp.json()

        result = data.get("market", {}).get("result", "")
        if result == "yes":
            return True
        if result == "no":
            return False
        return None

    except Exception as e:
        print(f"[Paper] Kalshi resolution error: {e}")
        return None


async def resolve_pending(fallback_btc: float) -> list[dict]:
    """
    Resolve open trades whose close_time has passed.

    1. Query Kalshi for the market result field — resolves within seconds of close.
    2. If not resolved yet and 10+ min have passed, fall back to Binance direction.
    """
    ledger   = _load()
    now      = datetime.now(timezone.utc)
    resolved = []

    for t in ledger["trades"]:
        if t["result"] is not None:
            continue

        close_field = t.get("close_time") or t.get("market_end", "")
        try:
            end_dt = datetime.fromisoformat(close_field.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue

        if now < end_dt:
            continue

        if now < end_dt + timedelta(minutes=2):
            continue

        up_won = await _kalshi_outcome(t.get("ticker", ""))

        if up_won is None:
            if now < end_dt + timedelta(minutes=10):
                continue
            up_won = fallback_btc > t["entry_btc"]
            print(f"[Paper] Using Binance fallback for resolution (Kalshi not resolved yet)")

        won   = (t["direction"] == "BULL" and up_won) or (t["direction"] == "BEAR" and not up_won)
        price = t["yes_price"] if t["direction"] == "BULL" else t["no_price"]
        size  = t["size_usdc"]
        pnl   = round((size / price) - size, 4) if won else -size

        t["result"]   = "WIN" if won else "LOSS"
        t["exit_btc"] = round(fallback_btc, 2)
        t["pnl"]      = pnl

        ledger["balance"] = round(ledger["balance"] + pnl, 4)
        resolved.append(t)

    if resolved:
        _save(ledger)

    return resolved
