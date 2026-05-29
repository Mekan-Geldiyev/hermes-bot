"""
Lightweight HTTP API server for the Hermes paper trading bot.
Exposes trade ledger and live status so the dashboard can read real data.

Endpoints:
  GET /trades   → full paper_trades.json ledger
  GET /status   → { running, last_price, last_tick }

Runs on port 8080 (configurable via API_PORT env var).
CORS is open so the Next.js frontend can reach it from any origin.
"""
import os
import time
from datetime import datetime, timezone

from aiohttp import web

from hermes.paper_trader import _load as load_ledger

_status: dict = {
    "running": True,
    "last_price": 0.0,
    "last_tick": None,
    "mode": "paper",
}

API_PORT = int(os.getenv("API_PORT", "8080"))


def update_status(price: float) -> None:
    _status["last_price"] = price
    _status["last_tick"]  = datetime.now(timezone.utc).isoformat()


# ─── handlers ─────────────────────────────────────────────────────────────────

async def handle_trades(request: web.Request) -> web.Response:
    return web.json_response(load_ledger())


async def handle_status(request: web.Request) -> web.Response:
    return web.json_response(_status)


# ─── CORS middleware ───────────────────────────────────────────────────────────

@web.middleware
async def cors(request: web.Request, handler):
    if request.method == "OPTIONS":
        return web.Response(headers={
            "Access-Control-Allow-Origin":  "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        })
    resp = await handler(request)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


# ─── startup ──────────────────────────────────────────────────────────────────

async def start() -> None:
    app = web.Application(middlewares=[cors])
    app.router.add_get("/trades", handle_trades)
    app.router.add_get("/status", handle_status)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", API_PORT)
    await site.start()
    print(f"[API] Serving on http://0.0.0.0:{API_PORT}  (trades, status)")
