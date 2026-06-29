"""
Claude Opus 4 as the synthesis brain.
Receives all quantitative signals, returns a structured trading decision.
"""
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import anthropic

from hermes.config import ANTHROPIC_API_KEY
from hermes.analysis.markov import MarkovResult
from hermes.analysis.monte_carlo import MCResult
from hermes.analysis.smc import SMCResult
from hermes.analysis.macro import MacroResult


@dataclass
class TradeDecision:
    direction: Optional[str]   # "BULL" | "BEAR" | "NO_TRADE"
    confidence: float          # 0.0–1.0
    reasoning: str
    raw_response: str


_SYSTEM_PROMPT = """You are Hermes, a quantitative trading brain for Kalshi BTC Up/Down markets.
You receive signal groups computed from live Binance microstructure data:
1. Markov chain persistence (momentum signal)
2. Monte Carlo path simulation (probabilistic forward projection)
3. Smart Money Concepts: BOS, Liquidity Sweep, FVG (structural/institutional signals)
4. Macro trend: 12-hour BTC price change (regime context)

Your job is to synthesise these signals and output a single JSON trading decision.
The market pays $1 if BTC closes higher (BULL) or lower (BEAR) than open in a 15-minute window.

Strict rules:
- Recommend BULL or BEAR only when BOTH of these hold:
  1. Markov AND MonteCarlo agree on the same direction.
  2. At least ONE of the following is also true:
     (a) At least one SMC signal (BOS, Liquidity Sweep, or FVG) confirms that direction, OR
     (b) Markov persistence > 0.58 AND MC probability > 0.57 for that direction.
- Output NO_TRADE if Markov and MC disagree, or neither condition (a) nor (b) is met.
- Macro context: a 12h move strongly opposing your direction (e.g. +1.5% when you want BEAR)
  is a significant red flag. Lower your confidence or output NO_TRADE if macro contradicts.
- Confidence must reflect genuine edge, not optimism. 0.5 = coin flip.
- Be terse. Reasoning ≤ 2 sentences.

Output ONLY valid JSON, no markdown:
{"direction": "BULL"|"BEAR"|"NO_TRADE", "confidence": 0.00, "reasoning": "..."}"""


def _build_user_message(
    btc_price: float,
    markov: MarkovResult,
    mc: MCResult,
    smc: SMCResult,
    macro: MacroResult,
    yes_price: float,
    no_price: float,
    window_open: datetime,
    window_end: datetime,
) -> str:
    now = datetime.now(window_end.tzinfo)
    mins_elapsed   = int((now - window_open).total_seconds() // 60)
    mins_remaining = int((window_end - now).total_seconds() // 60)

    macro_line = (
        f"12h BTC change: {macro.change_pct:+.2f}% → {macro.trend}  "
        f"(${macro.close_12h_ago:,.0f} → ${macro.close_now:,.0f})"
    )

    return f"""LIVE WINDOW: {window_open.strftime('%H:%M')}–{window_end.strftime('%H:%M')} UTC | {mins_elapsed}m elapsed, {mins_remaining}m remaining
This is the CURRENT active window. Your decision will be traded on this window only.

Current BTC price: ${btc_price:,.2f}
Kalshi YES (Up) ask: {yes_price:.3f} | NO (Down) ask: {no_price:.3f}

=== MACRO TREND (12h) ===
{macro_line}

=== MARKOV CHAIN ({markov.n_samples} samples) ===
P(Bull→Bull): {markov.bull_persistence:.3f}  |  P(Bear→Bear): {markov.bear_persistence:.3f}
Current state: {"BULL" if markov.current_state == 1 else "BEAR"}
Persistence threshold met: {markov.signal or "NONE"}

=== MONTE CARLO ({mc.n_paths} paths × {mc.n_steps} steps) ===
P(end=BULL): {mc.bull_prob:.3f}  |  P(end=BEAR): {mc.bear_prob:.3f}
MC signal: {mc.signal or "NONE"}

=== SMART MONEY CONCEPTS ===
BOS:              {smc.bos or "NONE"}
Liquidity Sweep:  {smc.liquidity_sweep or "NONE"}
Fair Value Gap:   {smc.fvg or "NONE"}
SMC consensus:    {smc.signal or "NONE"} ({smc.patterns_found}/3 patterns active)

Based on these signals, output your JSON trading decision."""


def query_claude(
    btc_price: float,
    markov: MarkovResult,
    mc: MCResult,
    smc: SMCResult,
    macro: MacroResult,
    yes_price: float,
    no_price: float,
    window_open: datetime,
    window_end: datetime,
) -> TradeDecision:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_msg = _build_user_message(
        btc_price, markov, mc, smc, macro,
        yes_price, no_price, window_open, window_end,
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = message.content[0].text.strip()

    # Strip markdown code fences if Claude wrapped the JSON
    clean = raw
    if clean.startswith("```"):
        clean = re.sub(r"^```[a-z]*\n?", "", clean).rstrip("`").strip()

    # Fall back to extracting the first JSON object if there's surrounding text
    if not clean.startswith("{"):
        m = re.search(r"\{[^{}]*\}", clean, re.DOTALL)
        clean = m.group() if m else clean

    try:
        parsed = json.loads(clean)
        return TradeDecision(
            direction=parsed.get("direction", "NO_TRADE"),
            confidence=float(parsed.get("confidence", 0.0)),
            reasoning=parsed.get("reasoning", ""),
            raw_response=raw,
        )
    except json.JSONDecodeError:
        return TradeDecision(
            direction="NO_TRADE",
            confidence=0.0,
            reasoning="Failed to parse Claude response",
            raw_response=raw,
        )
