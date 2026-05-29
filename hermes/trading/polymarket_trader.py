"""
Polymarket trade execution via py-clob-client.
Handles auth, order sizing, and submission.
"""
from dataclasses import dataclass
from typing import Optional

from hermes.config import (
    POLYMARKET_PRIVATE_KEY,
    POLYMARKET_API_KEY,
    POLYMARKET_API_SECRET,
    POLYMARKET_API_PASSPHRASE,
    CLOB_HOST,
    POLYGON_CHAIN_ID,
    MAX_TRADE_USDC,
)
from hermes.feeds.polymarket_feed import BTCMarket


@dataclass
class OrderResult:
    success: bool
    order_id: Optional[str]
    token_id: str
    direction: str
    amount_usdc: float
    price: float
    error: Optional[str] = None


def _get_client():
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds

    return ClobClient(
        host=CLOB_HOST,
        key=POLYMARKET_PRIVATE_KEY,
        chain_id=POLYGON_CHAIN_ID,
        creds=ApiCreds(
            api_key=POLYMARKET_API_KEY,
            api_secret=POLYMARKET_API_SECRET,
            api_passphrase=POLYMARKET_API_PASSPHRASE,
        ),
    )


def _kelly_size(edge: float, price: float, max_usdc: float) -> float:
    """
    Fractional Kelly for binary prediction market.
    edge = (true_prob - price) / (1 - price)  for YES bet
    Kelly fraction f = edge / (1 - price)  simplified for binary.
    Capped at MAX_TRADE_USDC and halved (half-Kelly).
    """
    if price <= 0 or price >= 1:
        return 0.0
    true_prob = price + edge
    if true_prob <= price:
        return 0.0
    # Standard Kelly: f = (b*p - q) / b  where b = (1-price)/price odds
    b = (1 - price) / price
    p = true_prob
    q = 1 - p
    kelly_f = (b * p - q) / b
    if kelly_f <= 0:
        return 0.0
    half_kelly_usdc = kelly_f * 0.5 * max_usdc
    return min(half_kelly_usdc, max_usdc)


def place_market_order(
    market: BTCMarket,
    direction: str,           # "BULL" or "BEAR"
    confidence: float,        # 0–1 from Claude
    max_usdc: float = MAX_TRADE_USDC,
) -> OrderResult:
    from py_clob_client.clob_types import MarketOrderArgs, OrderType

    if direction == "BULL":
        token_id = market.yes_token_id
        price    = market.yes_price
    else:
        token_id = market.no_token_id
        price    = market.no_price

    # Edge estimate: Claude confidence above fair 50/50 baseline
    implied_edge = max(0.0, confidence - price)
    amount_usdc  = _kelly_size(implied_edge, price, max_usdc)

    if amount_usdc < 1.0:
        return OrderResult(
            success=False,
            order_id=None,
            token_id=token_id,
            direction=direction,
            amount_usdc=0.0,
            price=price,
            error=f"Kelly size too small (${amount_usdc:.2f}), skip",
        )

    try:
        client = _get_client()
        order_args = MarketOrderArgs(token_id=token_id, amount=amount_usdc)
        signed = client.create_market_order(order_args)
        resp   = client.post_order(signed, OrderType.FOK)

        order_id = resp.get("orderID") or resp.get("id")
        return OrderResult(
            success=True,
            order_id=order_id,
            token_id=token_id,
            direction=direction,
            amount_usdc=amount_usdc,
            price=price,
        )
    except Exception as e:
        return OrderResult(
            success=False,
            order_id=None,
            token_id=token_id,
            direction=direction,
            amount_usdc=amount_usdc,
            price=price,
            error=str(e),
        )
