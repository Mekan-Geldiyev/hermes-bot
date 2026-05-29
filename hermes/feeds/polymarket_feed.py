"""
Polymarket market discovery via Gamma API.
Returns active Bitcoin Up/Down markets with their token IDs.
"""
import re
from dataclasses import dataclass
from typing import Optional

import aiohttp

from hermes.config import GAMMA_HOST


@dataclass
class BTCMarket:
    condition_id: str
    question: str
    end_date_iso: str
    yes_token_id: str
    no_token_id: str
    yes_price: float   # current mid-price for YES (Up) share
    no_price: float


async def get_active_btc_markets() -> list[BTCMarket]:
    """
    Query Gamma API for active short-window BTC Up/Down markets.
    These are the 15-minute window prediction markets.
    """
    url = f"{GAMMA_HOST}/markets"
    params = {
        "active": "true",
        "closed": "false",
        "tag_slug": "crypto",
        "limit": 100,
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            data = await resp.json()

    results = []
    for m in data:
        q = m.get("question", "")
        if "Bitcoin Up or Down" not in q and "Bitcoin up or down" not in q.lower():
            continue

        tokens = m.get("tokens", [])
        if len(tokens) < 2:
            continue

        yes_tok = next((t for t in tokens if t.get("outcome", "").lower() in ("yes", "up")), None)
        no_tok  = next((t for t in tokens if t.get("outcome", "").lower() in ("no", "down")), None)
        if not yes_tok or not no_tok:
            continue

        results.append(BTCMarket(
            condition_id=m["conditionId"],
            question=q,
            end_date_iso=m.get("endDate", ""),
            yes_token_id=yes_tok["token_id"],
            no_token_id=no_tok["token_id"],
            yes_price=float(yes_tok.get("price", 0.5)),
            no_price=float(no_tok.get("price", 0.5)),
        ))

    # Sort by soonest resolution first
    results.sort(key=lambda x: x.end_date_iso)
    return results


async def get_clob_order_book(token_id: str) -> dict:
    """Raw CLOB order book for a token."""
    url = f"https://clob.polymarket.com/book"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params={"token_id": token_id}) as resp:
            return await resp.json()
