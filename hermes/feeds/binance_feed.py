"""
Binance real-time feed.
- aggTrade WebSocket → 5-second price bars for Markov/MC
- REST /klines       → 1-minute OHLCV candles for SMC
"""
import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import aiohttp
import websockets

from hermes.config import (
    BINANCE_WS_URL, BINANCE_REST_URL,
    TICK_HISTORY, TICK_INTERVAL_SECONDS, CANDLE_HISTORY,
)


@dataclass
class Bar:
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class BinanceFeed:
    prices: deque = field(default_factory=lambda: deque(maxlen=TICK_HISTORY))
    candles: deque = field(default_factory=lambda: deque(maxlen=CANDLE_HISTORY))
    last_price: float = 0.0
    _bar_start: float = 0.0
    _bar_open: float = 0.0
    _bar_high: float = 0.0
    _bar_low: float = 9999999.0
    _bar_vol: float = 0.0

    def _flush_bar(self):
        if self._bar_open == 0.0:
            return
        bar = Bar(
            timestamp=self._bar_start,
            open=self._bar_open,
            high=self._bar_high,
            low=self._bar_low,
            close=self.last_price,
            volume=self._bar_vol,
        )
        self.prices.append(bar.close)

    def _update_bar(self, price: float, qty: float):
        now = time.time()
        bucket = int(now // TICK_INTERVAL_SECONDS) * TICK_INTERVAL_SECONDS

        if bucket != self._bar_start:
            self._flush_bar()
            self._bar_start = bucket
            self._bar_open = price
            self._bar_high = price
            self._bar_low = price
            self._bar_vol = 0.0

        self._bar_high = max(self._bar_high, price)
        self._bar_low = min(self._bar_low, price)
        self._bar_vol += qty
        self.last_price = price

    async def stream(self):
        while True:
            try:
                async with websockets.connect(BINANCE_WS_URL, ping_interval=20) as ws:
                    print("[Binance] WebSocket connected")
                    async for raw in ws:
                        msg = json.loads(raw)
                        price = float(msg["p"])
                        qty   = float(msg["q"])
                        self._update_bar(price, qty)
            except Exception as e:
                print(f"[Binance] WS error: {e} — reconnecting in 3s")
                await asyncio.sleep(3)

    async def refresh_candles(self):
        """Pull latest 1m candles; called periodically by main loop."""
        url = f"{BINANCE_REST_URL}/klines"
        params = {"symbol": "BTCUSDT", "interval": "1m", "limit": CANDLE_HISTORY}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    data = await resp.json()
            self.candles.clear()
            for row in data:
                self.candles.append(Bar(
                    timestamp=int(row[0]) / 1000,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                ))
        except Exception as e:
            print(f"[Binance] candle refresh error: {e}")

    async def preload(self) -> None:
        """Fetch historical 1m closes and pre-fill the price buffer so the
        feed is immediately ready without waiting for WebSocket to accumulate bars."""
        await self.refresh_candles()
        if self.candles:
            for bar in self.candles:
                self.prices.append(bar.close)
            self.last_price = list(self.candles)[-1].close
            print(f"[Binance] Preloaded {len(self.prices)} prices  last=${self.last_price:,.0f}")

    def ready(self) -> bool:
        return len(self.prices) >= 30
