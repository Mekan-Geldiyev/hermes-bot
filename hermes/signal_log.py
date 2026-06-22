"""
Observational logging for every signal that did NOT result in a trade because
confidence fell outside the validated [MIN_TRADE_CONFIDENCE, MAX_TRADE_CONFIDENCE]
band (see config.py). No money or contracts are ever involved here — purely
for building a dataset to evaluate the confidence-calibration hypothesis from
the 32-trade audit (extreme confidence correlates with trend exhaustion, not
continuation, on this timeframe).

- low_signal_log.json        : quant signals never converged — Claude was
                                never called (lightest — just the 3 raw votes)
- low_confidence_skips.json  : confidence < MIN_TRADE_CONFIDENCE (lightweight)
- high_confidence_log.json   : confidence > MAX_TRADE_CONFIDENCE (rich — full
                                signal breakdown + volatility context, to test
                                whether fading these is justified later)
"""
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

NO_CONVERGENCE_LOG_PATH = os.path.join(os.path.dirname(__file__), "low_signal_log.json")
LOW_LOG_PATH             = os.path.join(os.path.dirname(__file__), "low_confidence_skips.json")
HIGH_LOG_PATH            = os.path.join(os.path.dirname(__file__), "high_confidence_log.json")


def _load(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def _save(path: str, entries: list) -> None:
    with open(path, "w") as f:
        json.dump(entries, f, indent=2)


# ─── no-convergence (lightest — Claude was never called) ───────────────────────

def record_no_convergence(
    ticker: str,
    market_title: str,
    markov_signal: Optional[str],
    mc_signal: Optional[str],
    smc_signal: Optional[str],
) -> None:
    entries = _load(NO_CONVERGENCE_LOG_PATH)
    entries.append({
        "id":            datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "ticker":        ticker,
        "market":        market_title,
        "markov_signal": markov_signal,
        "mc_signal":     mc_signal,
        "smc_signal":    smc_signal,
        "note":          "skipped: no_convergence",
    })
    _save(NO_CONVERGENCE_LOG_PATH, entries)


# ─── low-confidence (lightweight) ──────────────────────────────────────────────

def record_low_confidence_skip(
    market_title: str,
    ticker: str,
    close_time: str,
    direction: str,
    entry_btc_price: float,
    yes_price: float,
    no_price: float,
    confidence: float,
    reasoning: str,
) -> None:
    entries = _load(LOW_LOG_PATH)
    entries.append({
        "id":             datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "market":         market_title,
        "ticker":         ticker,
        "close_time":     close_time,
        "direction":      direction,
        "entry_btc":      round(entry_btc_price, 2),
        "yes_price":      yes_price,
        "no_price":       no_price,
        "confidence":     round(confidence, 4),
        "reasoning":      reasoning,
        "would_have_won": None,
        "exit_btc":       None,
    })
    _save(LOW_LOG_PATH, entries)
    print(f"[LowConfSkip] Logged {direction} conf={confidence:.2f} — {market_title}")


# ─── high-confidence (rich) ─────────────────────────────────────────────────────

def record_high_confidence_signal(
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
    markov_current_state: int,
    markov_persistence: float,
    markov_bull_persistence: float,
    markov_bear_persistence: float,
    markov_n_samples: int,
    mc_signal: Optional[str],
    mc_bull_prob: float,
    mc_bear_prob: float,
    mc_n_paths: int,
    mc_n_steps: int,
    smc_bos: Optional[str],
    smc_liquidity_sweep: Optional[str],
    smc_fvg: Optional[str],
    smc_signal: Optional[str],
    smc_patterns_found: int,
    pct_change_5m: Optional[float],
    pct_change_15m: Optional[float],
    bars_since_state_flip: Optional[int],
    seconds_since_state_flip: Optional[float],
) -> None:
    entries = _load(HIGH_LOG_PATH)
    entries.append({
        "id":         datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "market":     market_title,
        "ticker":     ticker,
        "close_time": close_time,
        "direction":  direction,
        "entry_btc":  round(entry_btc_price, 2),
        "yes_price":  yes_price,
        "no_price":   no_price,
        "confidence": round(confidence, 4),
        "reasoning":  reasoning,
        "markov": {
            "signal":           markov_signal,
            "current_state":    "BULL" if markov_current_state == 1 else "BEAR",
            "persistence":      round(markov_persistence, 4),
            "bull_persistence": round(markov_bull_persistence, 4),
            "bear_persistence": round(markov_bear_persistence, 4),
            "n_samples":        markov_n_samples,
        },
        "monte_carlo": {
            "signal":    mc_signal,
            "bull_prob": round(mc_bull_prob, 4),
            "bear_prob": round(mc_bear_prob, 4),
            "n_paths":   mc_n_paths,
            "n_steps":   mc_n_steps,
        },
        "smc": {
            "bos":             smc_bos,
            "liquidity_sweep": smc_liquidity_sweep,
            "fvg":             smc_fvg,
            "signal":          smc_signal,
            "patterns_found":  smc_patterns_found,
        },
        "volatility": {
            "pct_change_5m":  round(pct_change_5m, 4) if pct_change_5m is not None else None,
            "pct_change_15m": round(pct_change_15m, 4) if pct_change_15m is not None else None,
        },
        "bars_since_state_flip":    bars_since_state_flip,
        "seconds_since_state_flip": seconds_since_state_flip,
        "would_have_won": None,
        "exit_btc":       None,
    })
    _save(HIGH_LOG_PATH, entries)
    print(f"[HighConfLog] Logged {direction} conf={confidence:.2f} — {market_title}")


# ─── resolution (shared) ────────────────────────────────────────────────────────

async def _resolve(path: str, fallback_btc: float) -> list:
    from hermes.paper_trader import _kalshi_outcome

    entries  = _load(path)
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
        _save(path, entries)
    return resolved


async def resolve_low_confidence_skips(fallback_btc: float) -> list:
    return await _resolve(LOW_LOG_PATH, fallback_btc)


async def resolve_high_confidence_log(fallback_btc: float) -> list:
    return await _resolve(HIGH_LOG_PATH, fallback_btc)
