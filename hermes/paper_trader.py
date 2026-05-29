"""
Paper trading ledger for Hermes.

Writes every simulated trade to hermes/paper_trades.json.
Tracks running account balance starting from ACCOUNT_SIZE_USDC.
Resolves trades automatically once the market's end time has passed,
using the live BTC price to determine win/loss.

P&L maths (prediction market binary):
  - You spend $size buying shares at price p (e.g. YES at 0.42)
  - Shares bought = size / p
  - WIN: receive $1 per share → pnl = (size/p) - size = size*(1-p)/p
  - LOSE: lose your stake → pnl = -size
"""
import json
import os
from datetime import datetime, timezone
from typing import Optional

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

def kelly_size(confidence: float, price: float, balance: float) -> float:
    """Half-Kelly on a binary prediction market bet, capped at MAX_POSITION_PCT."""
    if price <= 0.0 or price >= 1.0 or confidence <= price:
        return 0.0
    b = (1.0 - price) / price          # decimal odds
    kelly_f = (b * confidence - (1.0 - confidence)) / b
    if kelly_f <= 0.0:
        return 0.0
    raw = kelly_f * 0.5 * balance      # half-Kelly
    return round(min(raw, balance * MAX_POSITION_PCT), 2)


# ─── record ───────────────────────────────────────────────────────────────────

def record_trade(
    market_question: str,
    market_end: str,
    direction: str,
    entry_btc_price: float,
    yes_price: float,
    no_price: float,
    confidence: float,
    reasoning: str,
) -> Optional[dict]:
    """
    Log a paper trade. Returns the trade dict, or None if size is too small.
    """
    ledger  = _load()
    balance = ledger["balance"]
    price   = yes_price if direction == "BULL" else no_price
    size    = kelly_size(confidence, price, balance)

    if size < 0.05:
        print(f"[Paper] Size ${size:.2f} too small, skip")
        return None

    trade = {
        "id":            datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "market":        market_question,
        "market_end":    market_end,
        "direction":     direction,
        "entry_btc":     round(entry_btc_price, 2),
        "yes_price":     yes_price,
        "no_price":      no_price,
        "confidence":    round(confidence, 4),
        "reasoning":     reasoning,
        "size_usdc":     size,
        "result":        None,
        "exit_btc":      None,
        "pnl":           None,
    }

    ledger["trades"].append(trade)
    _save(ledger)

    print(
        f"[Paper] 📋 LOGGED {direction} | size=${size:.2f} | "
        f"odds={price:.3f} | conf={confidence:.0%} | "
        f"balance=${balance:.2f} | market: {market_question}"
    )
    return trade


# ─── resolve ──────────────────────────────────────────────────────────────────

def resolve_pending(current_btc: float) -> list[dict]:
    """
    Resolve any open trades whose market end time has passed.
    Uses current_btc as the exit price to determine win/loss.
    Returns list of newly resolved trades.
    """
    ledger  = _load()
    now     = datetime.now(timezone.utc)
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

        direction = t["direction"]
        won = (
            (direction == "BULL" and current_btc > t["entry_btc"]) or
            (direction == "BEAR" and current_btc < t["entry_btc"])
        )

        price = t["yes_price"] if direction == "BULL" else t["no_price"]
        size  = t["size_usdc"]
        pnl   = round((size / price) - size, 4) if won else -size

        t["result"]   = "WIN" if won else "LOSS"
        t["exit_btc"] = round(current_btc, 2)
        t["pnl"]      = pnl

        ledger["balance"] = round(ledger["balance"] + pnl, 4)
        resolved.append(t)

    if resolved:
        _save(ledger)

    return resolved
