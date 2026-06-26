"""
Live order placement on Kalshi (V2 events/orders endpoint).
Uses contract-count orders: count = floor(size / price_per_contract).

Side convention (V2 API quotes everything in YES terms):
  BULL → side="bid"  (buying YES at yes_ask)
  BEAR → side="ask"  (selling YES at 1-no_ask, equivalent to buying NO at no_ask)
"""
from dataclasses import dataclass
from typing import Optional

import aiohttp

from hermes.feeds.kalshi_feed import KalshiMarket, kalshi_headers, KALSHI_BASE


@dataclass
class OrderResult:
    success:     bool
    direction:   str
    price:       float
    amount_usdc: float
    order_id:    Optional[str] = None
    error:       Optional[str] = None


async def place_kalshi_order(
    market: KalshiMarket,
    direction: str,
    confidence: float,
    max_usdc: float,
) -> OrderResult:
    from hermes.paper_trader import kelly_size, get_balance

    # cost_price = what we actually pay per contract (for sizing)
    # yes_price  = the YES-side price sent to the API (V2 quotes everything in YES)
    if direction == "BULL":
        side        = "bid"
        cost_price  = market.yes_ask
        yes_price   = market.yes_ask
    else:
        side        = "ask"
        cost_price  = market.no_ask
        yes_price   = round(1.0 - market.no_ask, 6)

    bal   = get_balance()
    size  = kelly_size(confidence, cost_price, bal)
    size  = min(size, max_usdc)
    count = int(size / cost_price) if cost_price > 0 else 0

    if count < 1:
        return OrderResult(
            success=False, direction=direction, price=cost_price,
            amount_usdc=size, error="size too small (< 1 contract)",
        )

    path = "/trade-api/v2/portfolio/events/orders"
    body = {
        "ticker":                     market.ticker,
        "side":                       side,
        "count":                      f"{count}.00",
        "price":                      f"{yes_price:.4f}",
        "time_in_force":              "fill_or_kill",
        "self_trade_prevention_type": "taker_at_cross",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{KALSHI_BASE}/portfolio/events/orders",
                headers=kalshi_headers("POST", path),
                json=body,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()

        if resp.status in (200, 201):
            return OrderResult(
                success=True,
                direction=direction,
                price=cost_price,
                amount_usdc=size,
                order_id=data.get("order_id", ""),
            )
        return OrderResult(
            success=False, direction=direction, price=cost_price,
            amount_usdc=size, error=str(data),
        )
    except Exception as e:
        return OrderResult(
            success=False, direction=direction, price=cost_price,
            amount_usdc=0, error=str(e),
        )
