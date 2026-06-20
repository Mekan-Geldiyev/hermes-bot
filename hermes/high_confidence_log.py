"""
Log for signals skipped because confidence >= HIGH_CONFIDENCE_SKIP_THRESHOLD.

Trade log audit showed these high-confidence calls had a 28.6% actual win
rate vs ~64% for the 0.60-0.65 band, so the bot no longer trades them. They
are logged here with the eventual outcome so we can later check whether
skipping was correct, or whether fading (taking the opposite side) would
have been even better.
"""
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

LOG_PATH = os.path.join(os.path.dirname(__file__), "high_confidence_skips.json")


def _load() -> list:
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH) as f:
        return json.load(f)


def _save(entries: list) -> None:
    with open(LOG_PATH, "w") as f:
        json.dump(entries, f, indent=2)


def record_skip(
    market_title: str,
    ticker: str,
    close_time: str,
    direction: str,
    entry_btc_price: float,
    yes_price: float,
    no_price: float,
    confidence: float,
    reasoning: str,
    markov_signal: Optional[str],
    markov_persistence: float,
    mc_signal: Optional[str],
    mc_bull_prob: float,
    smc_signal: Optional[str],
) -> None:
    entries = _load()
    entries.append({
        "id":                datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
        "timestamp":         datetime.now(timezone.utc).isoformat(),
        "market":            market_title,
        "ticker":            ticker,
        "close_time":        close_time,
        "direction":         direction,
        "entry_btc":         round(entry_btc_price, 2),
        "yes_price":         yes_price,
        "no_price":          no_price,
        "confidence":        round(confidence, 4),
        "reasoning":         reasoning,
        "markov_signal":     markov_signal,
        "markov_persistence": round(markov_persistence, 4),
        "mc_signal":         mc_signal,
        "mc_bull_prob":      round(mc_bull_prob, 4),
        "smc_signal":        smc_signal,
        "would_have_won":    None,
        "exit_btc":          None,
    })
    _save(entries)
    print(f"[HighConfSkip] Logged {direction} conf={confidence:.2f} — {market_title}")


async def resolve_skips(fallback_btc: float) -> list:
    """Fill in would_have_won for skipped signals whose window has closed."""
    from hermes.paper_trader import _kalshi_outcome

    entries  = _load()
    now      = datetime.now(timezone.utc)
    resolved = []

    for e in entries:
        if e["would_have_won"] is not None:
            continue
        try:
            end_dt = datetime.fromisoformat(e["close_time"].replace("Z", "+00:00"))
        except (ValueError, TypeError, KeyError):
            continue
        if now < end_dt + timedelta(minutes=2):
            continue

        up_won = await _kalshi_outcome(e.get("ticker", ""))
        if up_won is None:
            if now < end_dt + timedelta(minutes=10):
                continue
            up_won = fallback_btc > e["entry_btc"]

        won = (e["direction"] == "BULL" and up_won) or (e["direction"] == "BEAR" and not up_won)
        e["would_have_won"] = won
        e["exit_btc"]       = round(fallback_btc, 2)
        resolved.append(e)

    if resolved:
        _save(entries)
    return resolved
