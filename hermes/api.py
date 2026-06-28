"""
Lightweight HTTP API server for the Hermes paper trading bot.

Endpoints:
  GET /trades        → full paper_trades.json ledger
  GET /status        → { running, last_price, last_tick }
  GET /logs?n=100    → last N lines of hermes.log, colour-tagged

Runs on port 8080 (configurable via API_PORT env var).
CORS is open so the Next.js frontend can reach it from any origin.
"""
import json
import logging
import os
from datetime import datetime, timezone

from aiohttp import web

logging.getLogger("aiohttp.server").setLevel(logging.CRITICAL)

from hermes.paper_trader import _load as load_ledger
from hermes.signal_log import LOW_LOG_PATH, HIGH_LOG_PATH


def _load_json(path: str) -> list:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

_status: dict = {
    "running": True,
    "last_price": 0.0,
    "last_tick": None,
    "mode": "paper",
}

API_PORT = int(os.getenv("API_PORT", "8080"))

# hermes.log sits one directory above this file (repo root)
LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "hermes.log")


def update_status(price: float) -> None:
    _status["last_price"] = price
    _status["last_tick"]  = datetime.now(timezone.utc).isoformat()


# ─── log colour tagging ───────────────────────────────────────────────────────

def _tag_line(line: str) -> str:
    l = line.lower()
    if any(w in l for w in ["error", "traceback", "exception", "failed", "451", "rejected"]):
        return "error"
    if any(w in l for w in ["win ✓", "trade placed", "trade logged", "websocket connected"]):
        return "success"
    if any(w in l for w in ["no trade", "veto", "mismatch", "skip", "split"]):
        return "warn"
    if any(w in l for w in ["fire", "new market", "converge=true"]):
        return "highlight"
    if any(w in l for w in ["markov=", "mc=", "smc=", "converge="]):
        return "signal"
    return "info"


# ─── handlers ─────────────────────────────────────────────────────────────────

async def handle_trades(request: web.Request) -> web.Response:
    return web.json_response(load_ledger())


async def handle_status(request: web.Request) -> web.Response:
    return web.json_response(_status)


async def handle_skips(request: web.Request) -> web.Response:
    return web.json_response(_load_json(LOW_LOG_PATH))


async def handle_highconf(request: web.Request) -> web.Response:
    return web.json_response(_load_json(HIGH_LOG_PATH))


async def handle_logs(request: web.Request) -> web.Response:
    n = min(int(request.query.get("n", 150)), 500)
    try:
        with open(LOG_PATH, errors="replace") as f:
            all_lines = f.readlines()
        lines = [
            {"text": line.rstrip(), "tag": _tag_line(line)}
            for line in all_lines[-n:]
            if line.strip()
        ]
    except FileNotFoundError:
        lines = []
    return web.json_response({"lines": lines})


# ─── CORS middleware ───────────────────────────────────────────────────────────

@web.middleware
async def cors(request: web.Request, handler):
    if request.method == "OPTIONS":
        return web.Response(headers={
            "Access-Control-Allow-Origin":  "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        })
    try:
        resp = await handler(request)
    except Exception:
        resp = web.Response(status=500, text="Internal error")
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


# ─── startup ──────────────────────────────────────────────────────────────────

async def start() -> None:
    app = web.Application(middlewares=[cors])
    app.router.add_get("/trades",   handle_trades)
    app.router.add_get("/status",   handle_status)
    app.router.add_get("/logs",     handle_logs)
    app.router.add_get("/skips",    handle_skips)
    app.router.add_get("/highconf", handle_highconf)

    runner = web.AppRunner(app, access_log=None)  # silence the BadHttpMessage spam
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", API_PORT)
    await site.start()
    print(f"[API] Serving on http://0.0.0.0:{API_PORT}  (trades, status, logs)")
