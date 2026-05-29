"""
Smart Money Concepts pattern detection on 1-minute OHLCV candles.
Detects: BOS (Break of Structure), Liquidity Sweep, FVG (Fair Value Gap).
"""
from dataclasses import dataclass
from typing import Optional

from hermes.feeds.binance_feed import Bar


@dataclass
class SMCResult:
    bos: Optional[str]            # "BULL" | "BEAR" | None
    liquidity_sweep: Optional[str]
    fvg: Optional[str]
    signal: Optional[str]         # majority vote, or None
    patterns_found: int


def detect_bos(candles: list[Bar], lookback: int = 15) -> Optional[str]:
    """
    Break of Structure: current bar's high breaks above the lookback high (bullish BOS)
    or current bar's low breaks below the lookback low (bearish BOS).
    """
    if len(candles) < lookback + 1:
        return None

    window  = candles[-(lookback+1):-1]
    current = candles[-1]

    swing_high = max(c.high for c in window)
    swing_low  = min(c.low  for c in window)

    if current.high > swing_high:
        return "BULL"
    if current.low < swing_low:
        return "BEAR"
    return None


def detect_liquidity_sweep(candles: list[Bar], lookback: int = 8) -> Optional[str]:
    """
    Liquidity sweep: price wicks through a key level then closes back inside.
    - Bullish: wick below recent swing low, close above it → smart money swept sell-side liq
    - Bearish: wick above recent swing high, close below it → smart money swept buy-side liq
    """
    if len(candles) < lookback + 1:
        return None

    window  = candles[-(lookback+1):-1]
    current = candles[-1]

    recent_low  = min(c.low  for c in window)
    recent_high = max(c.high for c in window)

    if current.low < recent_low and current.close > recent_low:
        return "BULL"
    if current.high > recent_high and current.close < recent_high:
        return "BEAR"
    return None


def detect_fvg(candles: list[Bar]) -> Optional[str]:
    """
    Fair Value Gap (Imbalance) on last three candles.
    - Bullish FVG: candle[-3].high < candle[-1].low  (gap up, price left inefficiency)
    - Bearish FVG: candle[-3].low  > candle[-1].high (gap down)
    """
    if len(candles) < 3:
        return None

    c1, _c2, c3 = candles[-3], candles[-2], candles[-1]

    if c1.high < c3.low:
        return "BULL"
    if c1.low > c3.high:
        return "BEAR"
    return None


def _majority(signals: list[Optional[str]]) -> Optional[str]:
    found = [s for s in signals if s is not None]
    if not found:
        return None
    bulls = found.count("BULL")
    bears = found.count("BEAR")
    if bulls > bears:
        return "BULL"
    if bears > bulls:
        return "BEAR"
    return None  # split


def compute_smc(candles: list[Bar]) -> SMCResult:
    bos   = detect_bos(candles)
    sweep = detect_liquidity_sweep(candles)
    fvg   = detect_fvg(candles)

    all_signals = [bos, sweep, fvg]
    found = [s for s in all_signals if s is not None]

    return SMCResult(
        bos=bos,
        liquidity_sweep=sweep,
        fvg=fvg,
        signal=_majority(all_signals),
        patterns_found=len(found),
    )
