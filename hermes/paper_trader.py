"""
Paper trading ledger for Hermes.

Win/loss is determined by Polymarket's ACTUAL resolution outcome (Chainlink BTC/USD),
not by comparing Binance prices. This matters because Polymarket uses Chainlink as the
price source, which can diverge from Binance spot.

P&L maths (prediction market binary):
  - You spend $size buying shares at price p (e.g. YES at 0.42)
  - Shares bought = size / p
  - WIN: receive $1 per share → pnl = (size/p) - size
  - LOSE: lose your stake    → pnl = -size
"""
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiohttp

from hermes.config import ACCOUNT_SIZE_USDC, MAX_POSITION_PCT, GAMMA_HOST

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

def kelly_size(confidence: float, price: float, balance: float) -> float:
    if price <= 0.0 or price >= 1.0 or confidence <= price:
        return 0.0
    b = (1.0 - price) / price
    kelly_f = (b * confidence - (1.0 - confidence)) / b
    if kelly_f <= 0.0:
        return 0.0
    return round(min(kelly_f * 0.5 * balance, balance * MAX_POSITION_PCT), 2)


# ─── record ───────────────────────────────────────────────────────────────────

def record_trade(
    market_question: str,
    market_end: str,
    condition_id: str,
    direction: str,
    entry_btc_price: float,
    yes_price: float,
    no_price: float,
    confidence: float,
    reasoning: str,
) -> Optional[dict]:
    ledger  = _load()
    balance = ledger["balance"]
    price   = yes_price if direction == "BULL" else no_price
    size    = kelly_size(confidence, price, balance)

    if size < 0.05:
        print(f"[Paper] Size ${size:.2f} too small, skip")
        return None

    trade = {
        "id":           datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "market":       market_question,
        "market_end":   market_end,
        "condition_id": condition_id,
        "direction":    direction,
        "entry_btc":    round(entry_btc_price, 2),
        "yes_price":    yes_price,
        "no_price":     no_price,
        "confidence":   round(confidence, 4),
        "reasoning":    reasoning,
        "size_usdc":    size,
        "result":       None,
        "exit_btc":     None,
        "pnl":          None,
    }

    ledger["trades"].append(trade)
    _save(ledger)

    print(
        f"[Paper] 📋 LOGGED {direction} | size=${size:.2f} | "
        f"odds={price:.3f} | conf={confidence:.0%} | "
        f"balance=${balance:.2f} | market: {market_question}"
    )
    return trade


# ─── resolution via Polymarket (uses Chainlink, same as actual market) ────────

async def _polymarket_outcome(condition_id: str) -> Optional[bool]:
    """
    Returns True (Up won), False (Down won), or None (not resolved yet).
    Queries Polymarket's actual resolution — same Chainlink source they use.
    """
    if not condition_id:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{GAMMA_HOST}/markets",
                params={"conditionId": condition_id},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                data = await resp.json()

        if not data or not isinstance(data, list):
            return None

        m = data[0]
        if not m.get("closed", False):
            return None  # not resolved yet

        prices_str = m.get("outcomePrices", "")
        if not prices_str:
            return None

        prices = json.loads(prices_str)
        yes_final = float(prices[0])

        if yes_final >= 0.99:
            return True   # Up won
        if yes_final <= 0.01:
            return False  # Down won
        return None       # ambiguous / not resolved

    except Exception as e:
        print(f"[Paper] Resolution fetch error: {e}")
        return None


async def resolve_pending(fallback_btc: float) -> list[dict]:
    """
    Resolve open trades whose end time has passed.

    1. Try to fetch Polymarket's actual resolution (Chainlink-based) — accurate.
    2. If market not resolved yet and 10+ min have passed, fall back to
       Binance direction comparison — approximate but fast.
    """
    ledger   = _load()
    now      = datetime.now(timezone.utc)
    resolved = []

    for t in ledger["trades"]:
        if t["result"] is not None:
            continue

        try:
            end_dt = datetime.fromisoformat(t["market_end"].replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue

        if now < end_dt:
            continue

        # Wait at least 2 min after end before checking resolution
        if now < end_dt + timedelta(minutes=2):
            continue

        up_won = await _polymarket_outcome(t.get("condition_id", ""))

        if up_won is None:
            # Polymarket not resolved yet — fall back to Binance after 10 min
            if now < end_dt + timedelta(minutes=10):
                continue
            direction = t["direction"]
            up_won = fallback_btc > t["entry_btc"]
            print(f"[Paper] Using Binance fallback for resolution (Polymarket not resolved)")

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
