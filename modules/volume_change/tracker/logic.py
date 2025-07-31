import asyncio
import json
import time
from typing import Sequence

import httpx
import websockets
from modules.volume_change.config import (
    VolumeInfo,
    EXINFO_API_URL,
    _CACHE_TTL_SEC,
)
from modules.config import TICKER_BLACKLIST
from db.logic import upsert_volumes
from modules.volume_change.config import _FLUSH_INTERVAL_SEC
from modules.volume_change.config import _STREAM_URL

_cached_symbols: set[str] = set()
_cached_symbols_ts: float = 0.0


async def _get_trading_symbols() -> Sequence[str]:
    """
    Возвращает список активных фьючерсных пар, исключая чёрный список.

    Args:
        None

    Returns:
        Sequence[str]: Список торговых символов.
    """
    global _cached_symbols, _cached_symbols_ts
    now = time.time()
    if now - _cached_symbols_ts < _CACHE_TTL_SEC:
        return list(_cached_symbols)

    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.get(EXINFO_API_URL)
        resp.raise_for_status()
        symbols = [
            s["symbol"]
            for s in resp.json()["symbols"]
            if s["status"] == "TRADING"
            and not any(blacklisted.lower() in s["symbol"].lower() for blacklisted in TICKER_BLACKLIST)
        ]

    _cached_symbols = set(symbols)
    _cached_symbols_ts = now
    return symbols


async def _stream(symbols: Sequence[str]) -> None:
    """Читает WebSocket‑поток и пишет объёмы закрытых минутных свечей.
    
    Args:
        symbols: Последовательность торговых символов для отслеживания.
        
    Raises:
        websockets.exceptions.WebSocketException: При ошибках WebSocket соединения.
        json.JSONDecodeError: При ошибках парсинга JSON.
    """
    streams = "/".join(f"{s.lower()}@kline_1m" for s in symbols)
    url = f"{_STREAM_URL}?streams={streams}"

    buffer: list[VolumeInfo] = []
    last_flush = time.time()

    try:
        async with websockets.connect(url, ping_interval=20) as ws:
            async for raw in ws:
                data = json.loads(raw)["data"]
                kline = data["k"]
                if not kline["x"]:
                    continue

                buffer.append({
                    "symbol": data["s"], 
                    "volume": kline["q"], 
                    "time": kline["T"]
                })

                if time.time() - last_flush >= _FLUSH_INTERVAL_SEC:
                    await upsert_volumes(buffer)
                    buffer.clear()
                    last_flush = time.time()
    finally:
        if buffer:
            await upsert_volumes(buffer)


async def run_volume_tracker() -> None:
    """Точка входа для потокового трекера объёмов."""
    symbols = await _get_trading_symbols()
    while True:
        try:
            await _stream(symbols)
        except Exception as exc:
            print(f"WS reconnect in 5 s: {exc}")
            await asyncio.sleep(5)
