"""
Telegram notification helper — fire-and-forget async messages.
"""
import asyncio

import aiohttp

from hermes.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


async def send(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(url, json=payload)
    except Exception as e:
        print(f"[Telegram] send error: {e}")


def notify(text: str) -> None:
    """Synchronous wrapper — spawns a task if loop is running."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(send(text))
        else:
            loop.run_until_complete(send(text))
    except Exception:
        pass
