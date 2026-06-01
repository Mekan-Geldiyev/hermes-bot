"""
Polymarket market discovery.
BTC 5-minute Up/Down markets use slug: btc-updown-5m-{unix_timestamp}
where the timestamp is the window start time (rounded to 5-minute boundary).
"""
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import aiohttp

from hermes.config import GAMMA_HOST


@dataclass
class BTCMarket:
    condition_id: str
    question: str
    end_date_iso: str
    yes_token_id: str
    no_token_id: str
    yes_price: float
    no_price: float


WINDOW_SECONDS = 900  # 15-minute markets

def _window_slugs(n: int = 6) -> list[str]:
    """Current + next N fifteen-minute window slugs."""
    base = (int(time.time()) // WINDOW_SECONDS) * WINDOW_SECONDS
    return [f"btc-updown-15m-{base + i * WINDOW_SECONDS}" for i in range(n)]


async def get_active_btc_markets() -> list[BTCMarket]:
    now     = datetime.now(timezone.utc)
    results = []
    seen    = set()

    async with aiohttp.ClientSession() as session:
        for slug in _window_slugs(8):
            try:
                async with session.get(
                    f"{GAMMA_HOST}/events",
                    params={"slug": slug},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    data = await resp.json()
            except Exception:
                continue

            if not data or not isinstance(data, list):
                continue

            event   = data[0]
            end_str = event.get("endDate", "")

            try:
                end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                if end_dt <= now:
                    continue
            except (ValueError, AttributeError):
                continue

            for m in event.get("markets", []):
                cid = m.get("conditionId", "")
                if cid in seen:
                    continue

                try:
                    clob_ids = json.loads(m.get("clobTokenIds", "[]") or "[]")
                except Exception:
                    continue

                if len(clob_ids) < 2:
                    continue

                try:
                    prices    = json.loads(m.get("outcomePrices", '["0.5","0.5"]') or '["0.5","0.5"]')
                    yes_price = float(prices[0])
                    no_price  = float(prices[1])
                except Exception:
                    yes_price, no_price = 0.5, 0.5

                seen.add(cid)
                results.append(BTCMarket(
                    condition_id  = cid,
                    question      = m.get("question", event.get("title", slug)),
                    end_date_iso  = end_str,
                    yes_token_id  = clob_ids[0],
                    no_token_id   = clob_ids[1],
                    yes_price     = yes_price,
                    no_price      = no_price,
                ))

    results.sort(key=lambda x: x.end_date_iso)
    return results
