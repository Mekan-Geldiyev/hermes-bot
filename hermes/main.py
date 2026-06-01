"""
Hermes — main event loop.

Lifecycle per 15-minute Polymarket window:
  1. Wait for a new BTC Up/Down market to appear
  2. Collect 90 seconds of Binance tick data
  3. Run Markov → Monte Carlo → SMC
  4. Ask Claude to synthesise
  5. If all signals agree and confidence ≥ threshold → log paper trade (or place real order)
  6. Telegram notification either way
  7. Periodically resolve completed paper trades using live BTC price
"""
import asyncio
import traceback
from datetime import datetime, timezone

from hermes.config import (
    MARKOV_PERSISTENCE_THRESHOLD,
    MONTE_CARLO_PATHS,
    MONTE_CARLO_STEPS,
    MIN_CONFIDENCE,
    MAX_TRADE_USDC,
    PAPER_TRADE,
)
from hermes.feeds.binance_feed import BinanceFeed
from hermes.feeds.polymarket_feed import get_active_btc_markets, BTCMarket
from hermes.analysis.markov import compute_markov
from hermes.analysis.monte_carlo import run_monte_carlo
from hermes.analysis.smc import compute_smc
from hermes.brain.claude_agent import query_claude
from hermes.notifications.telegram_bot import notify, send
from hermes.notifications.email_alert import send_trade_alert, send_resolve_alert
from hermes.api import start as start_api, update_status as api_update_status


ANALYSIS_DELAY_SECONDS = 90
SCAN_INTERVAL_SECONDS  = 30
CANDLE_REFRESH_SECONDS = 60
RESOLVE_CHECK_SECONDS  = 60   # how often to check for trade resolution


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


async def analyse_and_trade(feed: BinanceFeed, market: BTCMarket):
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

    # ── Claude synthesis ──────────────────────────────────────────────────────
    decision = query_claude(
        btc_price=feed.last_price,
        markov=markov,
        mc=mc,
        smc=smc if smc else _null_smc(),
        yes_price=market.yes_price,
        no_price=market.no_price,
    )

    print(f"[Claude] dir={decision.direction} conf={decision.confidence:.2f} | {decision.reasoning}")

    # ── Gate: quant must agree with Claude ────────────────────────────────────
    if not converge:
        await send(
            f"🔴 <b>NO TRADE</b> — signals split\n"
            f"Market: {market.question}\n"
            f"Markov: {markov.signal} | MC: {mc.signal} | SMC: {smc_sig}\n"
            f"Claude: {decision.direction} ({decision.confidence:.0%})\n"
            f"Reason: {decision.reasoning}"
        )
        return

    if decision.direction == "NO_TRADE" or decision.confidence < MIN_CONFIDENCE:
        await send(
            f"🟡 <b>CLAUDE VETOED</b>\n"
            f"Market: {market.question}\n"
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

    # ── Execute ───────────────────────────────────────────────────────────────
    print(f"[Hermes] FIRE {decision.direction} on {market.question}")

    if PAPER_TRADE:
        from hermes.paper_trader import record_trade, get_balance
        trade = record_trade(
            market_question=market.question,
            market_end=market.end_date_iso,
            condition_id=market.condition_id,
            direction=decision.direction,
            entry_btc_price=feed.last_price,
            yes_price=market.yes_price,
            no_price=market.no_price,
            confidence=decision.confidence,
            reasoning=decision.reasoning,
        )
        if trade:
            price = trade["yes_price"] if decision.direction == "BULL" else trade["no_price"]
            bal   = get_balance()
            await send(
                f"📋 <b>PAPER TRADE LOGGED</b>\n"
                f"Market: {market.question}\n"
                f"Direction: {decision.direction}  |  Odds: {price:.3f}\n"
                f"Size: ${trade['size_usdc']:.2f} USDC  |  Balance: ${bal:.2f}\n"
                f"Claude: {decision.confidence:.0%} — {decision.reasoning}"
            )
            send_trade_alert(
                direction=decision.direction,
                market=market.question,
                size_usdc=trade["size_usdc"],
                price=price,
                confidence=decision.confidence,
                reasoning=decision.reasoning,
                balance=bal,
            )
        else:
            await send(f"📋 <b>PAPER SKIP</b> — size too small\nMarket: {market.question}")
    else:
        from hermes.trading.polymarket_trader import place_market_order
        result = place_market_order(market, decision.direction, decision.confidence, MAX_TRADE_USDC)
        if result.success:
            await send(
                f"✅ <b>TRADE PLACED</b>\n"
                f"Market: {market.question}\n"
                f"Direction: {result.direction}  |  Price: {result.price:.3f}\n"
                f"Size: ${result.amount_usdc:.2f} USDC  |  OrderID: {result.order_id}\n"
                f"Claude: {decision.confidence:.0%} — {decision.reasoning}"
            )
        else:
            await send(
                f"❌ <b>ORDER FAILED</b>\n"
                f"Market: {market.question}\n"
                f"Direction: {result.direction}  Error: {result.error}"
            )
        print(f"[Hermes] Order result: success={result.success} error={result.error}")


async def price_status_updater(feed: BinanceFeed):
    """Keep the API status endpoint current with the live BTC price."""
    while True:
        if feed.last_price:
            api_update_status(feed.last_price)
        await asyncio.sleep(5)


async def candle_refresher(feed: BinanceFeed):
    while True:
        await feed.refresh_candles()
        await asyncio.sleep(CANDLE_REFRESH_SECONDS)


async def trade_resolver(feed: BinanceFeed):
    """Periodically resolve completed paper trades using live BTC price."""
    if not PAPER_TRADE:
        return
    while True:
        await asyncio.sleep(RESOLVE_CHECK_SECONDS)
        if feed.last_price == 0.0:
            continue
        try:
            from hermes.paper_trader import resolve_pending, get_balance
            resolved = await resolve_pending(feed.last_price)
            for t in resolved:
                icon = "✅" if t["result"] == "WIN" else "❌"
                pnl_str = f"+${t['pnl']:.2f}" if t["pnl"] >= 0 else f"-${abs(t['pnl']):.2f}"
                bal = get_balance()
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
        except Exception:
            traceback.print_exc()


async def main_loop(feed: BinanceFeed):
    seen_markets: set[str] = set()
    await asyncio.sleep(5)

    mode = "PAPER TRADING" if PAPER_TRADE else "LIVE TRADING"
    print(f"[Hermes] Scanner started — {mode} — polling every {SCAN_INTERVAL_SECONDS}s")
    notify(f"🟢 <b>Hermes online [{mode}]</b> — scanning Polymarket for BTC Up/Down windows")

    while True:
        try:
            markets = await get_active_btc_markets()

            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            new = [m for m in markets if m.condition_id not in seen_markets]
            print(f"[{ts} UTC] Polymarket scan: {len(markets)} BTC markets live, {len(new)} new")

            for market in markets:
                if market.condition_id in seen_markets:
                    continue

                seen_markets.add(market.condition_id)
                print(f"[Hermes] New market: {market.question} (ends {market.end_date_iso})")
                await send(f"🔍 New market: <b>{market.question}</b>")

                print(f"[Hermes] Collecting {ANALYSIS_DELAY_SECONDS}s of data…")
                await asyncio.sleep(ANALYSIS_DELAY_SECONDS)

                if not feed.ready():
                    print("[Hermes] Feed not ready, skip")
                    continue

                await analyse_and_trade(feed, market)

        except Exception:
            print("[Hermes] Scanner error:")
            traceback.print_exc()

        await asyncio.sleep(SCAN_INTERVAL_SECONDS)


async def run():
    feed = BinanceFeed()
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
