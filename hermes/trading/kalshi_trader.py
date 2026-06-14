"""
Live order placement on Kalshi.
Uses contract-count orders: count = floor(size / price_per_contract).
"""
import json
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

    side  = "yes" if direction == "BULL" else "no"
    price = market.yes_ask if direction == "BULL" else market.no_ask
    bal   = get_balance()
    size  = kelly_size(confidence, price, bal)
    size  = min(size, max_usdc)

    count = int(size / price) if price > 0 else 0

    if count < 1:
        return OrderResult(
            success=False, direction=direction, price=price,
            amount_usdc=size, error="size too small (< 1 contract)",
        )

    path      = "/trade-api/v2/portfolio/orders"
    price_key = "yes_price_dollars" if direction == "BULL" else "no_price_dollars"
    body      = {
        "ticker":   market.ticker,
        "action":   "buy",
        "side":     side,
        "type":     "limit",
        "count":    count,
        price_key:  f"{price:.2f}",
    }
    body_str = json.dumps(body)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{KALSHI_BASE}/portfolio/orders",
                headers=kalshi_headers("POST", path),
                data=body_str,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()

        if resp.status in (200, 201):
            order = data.get("order", {})
            return OrderResult(
                success=True,
                direction=direction,
                price=price,
                amount_usdc=size,
                order_id=order.get("order_id", ""),
            )
        return OrderResult(
            success=False, direction=direction, price=price,
            amount_usdc=size, error=str(data),
        )
    except Exception as e:
        return OrderResult(
            success=False, direction=direction, price=price,
            amount_usdc=0, error=str(e),
        )
