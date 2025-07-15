import httpx
from typing import Iterable
import time
from modules.price.config import PriceInfo, PRICE_API_URL, TICKER_BLACKLIST, _CACHE_TTL_SEC, EXINFO_API_URL, _ExSymbol, MAX_AGE_MS

_cached_symbols: set[str] = set()
_cached_symbols_ts: float = 0.0

async def _get_trading_symbols(client: httpx.AsyncClient) -> set[str]:
    """Возвращает кэш-сет всех символов со status == "TRADING"

    Кэш живёт _CACHE_TTL_SEC секунд, чтобы не бомбить API при каждом цикле.

    Args:
        client (httpx.AsyncClient): Асинхронный клиент для запросов.
    """
    global _cached_symbols_ts, _cached_symbols

    now = time.time()
    if now - _cached_symbols_ts < _CACHE_TTL_SEC:
        return _cached_symbols

    resp = await client.get(EXINFO_API_URL)
    resp.raise_for_status()
    symbols: Iterable[_ExSymbol] = resp.json()["symbols"]

    _cached_symbols = {s["symbol"] for s in symbols if s["status"] == "TRADING"}
    _cached_symbols_ts = now
    return _cached_symbols

async def fetch_price_info() -> list[PriceInfo]:
    """Возвращает цены только активных фьючерсных пар, исключая тикеры из чёрного списка.

    Returns:
        list[PriceInfo]: Список словарей с данными о цене, где для каждого элемента:
            symbol (str): Торговая пара, например ``"AMBUSDT"``.
            price (str): Цена в текстовом формате, полученная от Binance.
            time (int): Метка времени Binance в миллисекундах Unix.
    """
    async with httpx.AsyncClient(timeout=5) as client:
        trading = await _get_trading_symbols(client)

        resp = await client.get(PRICE_API_URL)
        resp.raise_for_status()
        raw = resp.json()

        now_ms = int(time.time() * 1000)
        lower_black = {t.lower() for t in TICKER_BLACKLIST}

        return [
            {"symbol": d["symbol"], "price": d["price"], "time": d["time"]}
            for d in raw
            if d["symbol"] in trading
            and d["symbol"].lower() not in lower_black
            and now_ms - int(d["time"]) < MAX_AGE_MS
        ]