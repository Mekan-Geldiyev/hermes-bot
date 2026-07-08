"""
Hermes — main event loop.

Lifecycle per 15-minute Kalshi window:
  1. Poll for the currently live BTC Up/Down market (KXBTC15M series)
  2. Collect 90 seconds of Binance tick data
  3. Run Markov → Monte Carlo → SMC
  4. Ask Claude to synthesise
  5. If all signals agree and confidence ≥ threshold → paper trade or live Kalshi order
  6. Telegram notification either way
  7. Periodically resolve completed trades using Kalshi result field
"""
import asyncio
import time
import traceback
from collections import deque
from datetime import datetime, timezone
from typing import Optional

# Circuit breaker: tracks (timestamp, direction) of resolved LOSS trades in-process.
# Shared between trade_resolver (writer) and analyse_and_trade (reader).
_recent_losses: deque = deque(maxlen=20)

from hermes.config import (
    MARKOV_PERSISTENCE_THRESHOLD,
    MONTE_CARLO_PATHS,
    MONTE_CARLO_STEPS,
    MIN_TRADE_CONFIDENCE,
    MAX_TRADE_USDC,
    MACRO_VETO_PCT,
    PAPER_TRADE,
    TICK_INTERVAL_SECONDS,
)
from hermes.feeds.binance_feed import BinanceFeed
from hermes.feeds.kalshi_feed import get_current_btc_market, KalshiMarket
from hermes.analysis.markov import compute_markov
from hermes.analysis.monte_carlo import run_monte_carlo
from hermes.analysis.smc import compute_smc
from hermes.analysis.macro import get_macro_trend
from hermes.brain.claude_agent import query_claude
from hermes.notifications.telegram_bot import notify, send
from hermes.notifications.email_alert import send_trade_alert, send_resolve_alert
from hermes.api import start as start_api, update_status as api_update_status


ANALYSIS_DELAY_SECONDS = 90
SCAN_INTERVAL_SECONDS  = 30
CANDLE_REFRESH_SECONDS = 60
RESOLVE_CHECK_SECONDS  = 60


def _signals_converge(markov_signal, mc_signal, smc_signal) -> tuple[bool, str]:
    votes   = [markov_signal, mc_signal, smc_signal]
    defined = [v for v in votes if v is not None]
    if len(defined) < 2:
        return False, "NO_TRADE"
    bulls = defined.count("BULL")
    bears = defined.count("BEAR")
    if bulls >= 2:
        return True, "BULL"
    if bears >= 2:
        return True, "BEAR"
    return False, "NO_TRADE"


def _null_smc():
    from hermes.analysis.smc import SMCResult
    return SMCResult(bos=None, liquidity_sweep=None, fvg=None, signal=None, patterns_found=0)


def _pct_change_over(prices: list[float], minutes: float) -> Optional[float]:
    """% price change over the prior N minutes, using the 5s-bar price buffer."""
    bars = int((minutes * 60) / TICK_INTERVAL_SECONDS)
    if bars <= 0 or len(prices) <= bars:
        return None
    past = prices[-1 - bars]
    if past == 0:
        return None
    return (prices[-1] - past) / past * 100


def _bars_since_state_flip(prices: list[float]) -> Optional[int]:
    """How many bars the Markov buffer has held its current BULL/BEAR state."""
    from hermes.analysis.markov import classify_returns
    states = classify_returns(prices)
    if len(states) < 2:
        return None
    last = states[-1]
    run = 0
    for s in reversed(states):
        if s != last:
            break
        run += 1
    return run


async def analyse_and_trade(feed: BinanceFeed, market: KalshiMarket, window_open: datetime, window_end: datetime):
    prices  = list(feed.prices)
    candles = list(feed.candles)

    if len(prices) < 30:
        print(f"[Hermes] Not enough price history ({len(prices)} bars), skip")
        return

    # ── Analysis ──────────────────────────────────────────────────────────────
    markov  = compute_markov(prices, MARKOV_PERSISTENCE_THRESHOLD)
    mc      = run_monte_carlo(
        markov.transition_matrix, markov.current_state,
        n_paths=MONTE_CARLO_PATHS, n_steps=MONTE_CARLO_STEPS,
    )
    smc     = compute_smc(candles) if len(candles) >= 5 else None
    smc_sig = smc.signal if smc else None

    converge, quant_direction = _signals_converge(markov.signal, mc.signal, smc_sig)

    print(
        f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC] "
        f"Markov={markov.signal}(persist={markov.persistence:.2f}) "
        f"MC={mc.signal}(bull={mc.bull_prob:.2f}) "
        f"SMC={smc_sig}({smc.patterns_found if smc else 0}/3) "
        f"Converge={converge}/{quant_direction}"
    )

    # ── Circuit breaker ───────────────────────────────────────────────────────
    cutoff = time.time() - 90 * 60  # 90-minute window
    recent_loss_count = sum(1 for ts, _ in _recent_losses if ts > cutoff)
    if recent_loss_count >= 2:
        print(f"[Hermes] CIRCUIT BREAKER — {recent_loss_count} losses in last 90m, skipping cycle")
        await send(
            f"⏸ <b>CIRCUIT BREAKER</b> — {recent_loss_count} losses in last 90 min\n"
            f"Market: {market.title}\nSkipping this cycle."
        )
        return

    # ── Short-term momentum (5-minute price recovery check) ───────────────────
    mom_pct = _pct_change_over(prices, 5) or 0.0
    mom_dir = "BULL" if mom_pct > 0.08 else "BEAR" if mom_pct < -0.08 else "NEUTRAL"

    # ── Gate: quant convergence required before Claude is ever called ──────────
    # No trade can fire without convergence, so querying Claude on a non-
    # converged cycle is a wasted API call. Check this first.
    if not converge:
        from hermes.signal_log import record_no_convergence
        record_no_convergence(
            ticker=market.ticker,
            market_title=market.title,
            markov_signal=markov.signal,
            mc_signal=mc.signal,
            smc_signal=smc_sig,
        )
        await send(
            f"🔴 <b>NO TRADE</b> — signals split\n"
            f"Market: {market.title}\n"
            f"Markov: {markov.signal} | MC: {mc.signal} | SMC: {smc_sig}"
        )
        return

    # ── Macro trend (12h BTC direction) ──────────────────────────────────────
    macro = await get_macro_trend()
    print(
        f"[Macro] 12h change={macro.change_pct:+.2f}% trend={macro.trend} "
        f"(${macro.close_12h_ago:,.0f} → ${macro.close_now:,.0f})"
    )

    # ── Claude synthesis ──────────────────────────────────────────────────────
    decision = query_claude(
        btc_price=feed.last_price,
        markov=markov,
        mc=mc,
        smc=smc if smc else _null_smc(),
        macro=macro,
        yes_price=market.yes_ask,
        no_price=market.no_ask,
        window_open=window_open,
        window_end=window_end,
        short_momentum_pct=mom_pct,
        short_momentum_dir=mom_dir,
    )

    print(f"[Claude] dir={decision.direction} conf={decision.confidence:.2f} | {decision.reasoning}")

    if decision.direction == "NO_TRADE":
        await send(
            f"🟡 <b>CLAUDE VETOED</b>\n"
            f"Market: {market.title}\n"
            f"Quant: {quant_direction} | Claude: {decision.direction} ({decision.confidence:.0%})\n"
            f"Reason: {decision.reasoning}"
        )
        return

    if decision.direction != quant_direction:
        await send(
            f"🟡 <b>DIRECTION MISMATCH</b> — quant={quant_direction} Claude={decision.direction}\n"
            f"Skipping."
        )
        return

    # ── Macro hard veto ───────────────────────────────────────────────────────
    macro_contradiction = (
        (decision.direction == "BEAR" and macro.change_pct >  MACRO_VETO_PCT) or
        (decision.direction == "BULL" and macro.change_pct < -MACRO_VETO_PCT)
    )
    if macro_contradiction:
        print(
            f"[Macro] VETO {decision.direction} — 12h BTC {macro.change_pct:+.2f}% "
            f"opposes signal (threshold ±{MACRO_VETO_PCT}%)"
        )
        await send(
            f"🚫 <b>MACRO VETO</b> — {decision.direction} blocked\n"
            f"Market: {market.title}\n"
            f"12h BTC: {macro.change_pct:+.2f}% ({macro.trend}) contradicts {decision.direction} signal.\n"
            f"Claude conf was {decision.confidence:.0%} — overridden by regime filter."
        )
        return

    # ── Confidence floor ────────────────────────────────────────────────────────
    if decision.confidence < MIN_TRADE_CONFIDENCE:
        from hermes.signal_log import record_low_confidence_skip
        record_low_confidence_skip(
            market_title=market.title,
            ticker=market.ticker,
            close_time=market.close_time,
            direction=decision.direction,
            entry_btc_price=feed.last_price,
            yes_price=market.yes_ask,
            no_price=market.no_ask,
            confidence=decision.confidence,
            reasoning=decision.reasoning,
        )
        await send(
            f"⚪ <b>LOW-CONFIDENCE SKIP</b> — conf={decision.confidence:.0%} (< {MIN_TRADE_CONFIDENCE:.0%} floor)\n"
            f"Market: {market.title}\n"
            f"Direction: {decision.direction}  |  Logged for tracking, not traded."
        )
        return

    # ── Value filter: avoid entering when market odds strongly oppose direction ──
    # Data: no_price < 0.44 for BEAR = 25% WR and -$10 total. Market is right.
    if decision.direction == "BEAR" and market.no_ask < 0.44:
        print(f"[Hermes] VALUE FILTER — BEAR skipped: no_price={market.no_ask:.3f} < 0.44 (market >56% UP)")
        await send(
            f"⛔ <b>VALUE FILTER</b> — BEAR skipped\n"
            f"Market: {market.title}\n"
            f"NO ask ({market.no_ask:.3f}) below 0.44 floor — market pricing >56% UP, no edge."
        )
        return
    if decision.direction == "BULL" and market.yes_ask < 0.44:
        print(f"[Hermes] VALUE FILTER — BULL skipped: yes_price={market.yes_ask:.3f} < 0.44 (market >56% DOWN)")
        await send(
            f"⛔ <b>VALUE FILTER</b> — BULL skipped\n"
            f"Market: {market.title}\n"
            f"YES ask ({market.yes_ask:.3f}) below 0.44 floor — market pricing >56% DOWN, no edge."
        )
        return

    # ── Execute ───────────────────────────────────────────────────────────────
    print(f"[Hermes] FIRE {decision.direction} on {market.title}")

    if PAPER_TRADE:
        from hermes.paper_trader import record_trade, get_balance
        trade = record_trade(
            market_title=market.title,
            close_time=market.close_time,
            ticker=market.ticker,
            direction=decision.direction,
            entry_btc_price=feed.last_price,
            yes_ask=market.yes_ask,
            no_ask=market.no_ask,
            confidence=decision.confidence,
            reasoning=decision.reasoning,
        )
        if trade:
            price = trade["yes_price"] if decision.direction == "BULL" else trade["no_price"]
            bal   = get_balance()
            await send(
                f"📋 <b>PAPER TRADE LOGGED</b>\n"
                f"Market: {market.title}\n"
                f"Direction: {decision.direction}  |  Odds: {price:.3f}\n"
                f"Size: ${trade['size_usdc']:.2f} USDC  |  Balance: ${bal:.2f}\n"
                f"Claude: {decision.confidence:.0%} — {decision.reasoning}"
            )
            send_trade_alert(
                direction=decision.direction,
                market=market.title,
                size_usdc=trade["size_usdc"],
                price=price,
                confidence=decision.confidence,
                reasoning=decision.reasoning,
                balance=bal,
            )
        else:
            await send(f"📋 <b>PAPER SKIP</b> — size too small\nMarket: {market.title}")
    else:
        from hermes.trading.kalshi_trader import place_kalshi_order
        result = await place_kalshi_order(market, decision.direction, decision.confidence, MAX_TRADE_USDC)
        if result.success:
            from hermes.paper_trader import record_trade, get_balance
            record_trade(
                market_title=market.title,
                close_time=market.close_time,
                ticker=market.ticker,
                direction=result.direction,
                entry_btc_price=feed.last_price,
                yes_ask=market.yes_ask,
                no_ask=market.no_ask,
                confidence=decision.confidence,
                reasoning=decision.reasoning,
                size_override=result.amount_usdc,
            )
            bal = get_balance()
            await send(
                f"✅ <b>TRADE PLACED</b>\n"
                f"Market: {market.title}\n"
                f"Direction: {result.direction}  |  Price: {result.price:.3f}\n"
                f"Size: ${result.amount_usdc:.2f} USDC  |  OrderID: {result.order_id}\n"
                f"Claude: {decision.confidence:.0%} — {decision.reasoning}"
            )
            send_trade_alert(
                direction=result.direction,
                market=market.title,
                size_usdc=result.amount_usdc,
                price=result.price,
                confidence=decision.confidence,
                reasoning=decision.reasoning,
                live=True,
                order_id=result.order_id or "",
            )
        else:
            await send(
                f"❌ <b>ORDER FAILED</b>\n"
                f"Market: {market.title}\n"
                f"Direction: {result.direction}  Error: {result.error}"
            )
        print(f"[Hermes] Order result: success={result.success} error={result.error}")


async def price_status_updater(feed: BinanceFeed):
    while True:
        if feed.last_price:
            api_update_status(feed.last_price)
        await asyncio.sleep(5)


async def candle_refresher(feed: BinanceFeed):
    while True:
        await feed.refresh_candles()
        await asyncio.sleep(CANDLE_REFRESH_SECONDS)


async def trade_resolver(feed: BinanceFeed):
    while True:
        await asyncio.sleep(RESOLVE_CHECK_SECONDS)
        if feed.last_price == 0.0:
            continue
        try:
            from hermes.paper_trader import resolve_pending, get_balance
            resolved = await resolve_pending(feed.last_price)
            for t in resolved:
                if t["result"] == "LOSS":
                    _recent_losses.append((time.time(), t["direction"]))
                icon    = "✅" if t["result"] == "WIN" else "❌"
                pnl_str = f"+${t['pnl']:.2f}" if t["pnl"] >= 0 else f"-${abs(t['pnl']):.2f}"
                bal     = get_balance()
                print(
                    f"[Paper] {icon} RESOLVED {t['direction']} | "
                    f"{t['result']} | P&L {pnl_str} | balance=${bal:.2f}"
                )
                await send(
                    f"{icon} <b>PAPER TRADE RESOLVED</b>\n"
                    f"Market: {t['market']}\n"
                    f"Direction: {t['direction']}  |  Result: {t['result']}\n"
                    f"Entry: ${t['entry_btc']:,.0f}  →  Exit: ${t['exit_btc']:,.0f}\n"
                    f"P&L: {pnl_str}  |  Balance: ${bal:.2f}"
                )
                send_resolve_alert(
                    direction=t["direction"],
                    result=t["result"],
                    entry_btc=t["entry_btc"],
                    exit_btc=t["exit_btc"],
                    pnl=t["pnl"],
                    balance=bal,
                    market=t["market"],
                )

            from hermes.signal_log import resolve_low_confidence_skips, resolve_high_confidence_log
            low_resolved = await resolve_low_confidence_skips(feed.last_price)
            for s in low_resolved:
                icon = "✅" if s["would_have_won"] else "❌"
                print(
                    f"[LowConfSkip] {icon} {s['direction']} conf={s['confidence']:.2f} "
                    f"would_have_won={s['would_have_won']} | {s['market']}"
                )

            high_resolved = await resolve_high_confidence_log(feed.last_price)
            for s in high_resolved:
                icon = "✅" if s["would_have_won"] else "❌"
                print(
                    f"[HighConfLog] {icon} {s['direction']} conf={s['confidence']:.2f} "
                    f"would_have_won={s['would_have_won']} | {s['market']}"
                )
        except Exception:
            traceback.print_exc()


async def main_loop(feed: BinanceFeed):
    seen_markets: set[str] = set()
    await asyncio.sleep(5)

    mode = "PAPER TRADING" if PAPER_TRADE else "LIVE TRADING"
    print(f"[Hermes] Scanner started — {mode} — polling every {SCAN_INTERVAL_SECONDS}s")
    notify(f"🟢 <b>Hermes online [{mode}]</b> — scanning Kalshi KXBTC15M")

    while True:
        try:
            market = await get_current_btc_market()
            ts     = datetime.now(timezone.utc).strftime("%H:%M:%S")

            if market is None:
                print(f"[{ts} UTC] Kalshi: no active BTC 15m window right now")
                await asyncio.sleep(SCAN_INTERVAL_SECONDS)
                continue

            if market.ticker in seen_markets:
                print(f"[{ts} UTC] Kalshi: {market.ticker} (already processed)")
                await asyncio.sleep(SCAN_INTERVAL_SECONDS)
                continue

            seen_markets.add(market.ticker)
            window_open = datetime.fromisoformat(market.open_time.replace("Z",  "+00:00"))
            window_end  = datetime.fromisoformat(market.close_time.replace("Z", "+00:00"))
            mins_left   = int((window_end - datetime.now(timezone.utc)).total_seconds() // 60)

            print(f"[Hermes] Live window: {market.title} | {market.ticker} ({mins_left}m remaining)")
            await send(f"🔍 Live window: <b>{market.title}</b> ({mins_left}m left) | floor=${market.floor_strike:,.2f}")

            print(f"[Hermes] Collecting {ANALYSIS_DELAY_SECONDS}s of data…")
            await asyncio.sleep(ANALYSIS_DELAY_SECONDS)

            if not feed.ready():
                print("[Hermes] Feed not ready, skip")
                await asyncio.sleep(SCAN_INTERVAL_SECONDS)
                continue

            await analyse_and_trade(feed, market, window_open, window_end)

        except Exception:
            print("[Hermes] Scanner error:")
            traceback.print_exc()

        await asyncio.sleep(SCAN_INTERVAL_SECONDS)


async def run():
    feed = BinanceFeed()
    await feed.preload()
    await asyncio.gather(
        start_api(),
        feed.stream(),
        candle_refresher(feed),
        trade_resolver(feed),
        price_status_updater(feed),
        main_loop(feed),
    )


if __name__ == "__main__":
    asyncio.run(run())
