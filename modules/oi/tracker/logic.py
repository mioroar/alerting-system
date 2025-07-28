import httpx
import asyncio
from typing import List

from modules.oi.config import EXINFO_API_URL, OI_API_URL, OIInfo, TICKER_BLACKLIST, _get_client
from config import logger


async def _get_perp_symbols() -> list[str]:
    """Возвращает список символов perpetual‑фьючерсов Binance.

    Исключает пары из ``TICKER_BLACKLIST``.

    Returns:
        list[str]: Список символов perpetual-фьючерсов, доступных для торговли.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(EXINFO_API_URL)
        data = resp.json()
        symbols = [
            s["symbol"]
            for s in data.get("symbols", [])
            if s.get("contractType") == "PERPETUAL"
            and s.get("status") == "TRADING"
            and not any(blk in s["symbol"] for blk in TICKER_BLACKLIST)
        ]
    return symbols


async def _fetch_single(symbol: str) -> OIInfo | None:
    """Получить OI для одного символа (с reuse клиента + семафор).

    Args:
        symbol: Символ торговой пары для получения данных OI.

    Returns:
        OIInfo | None: Информация об открытом интересе для символа или None в случае ошибки.
    """
    async with asyncio.Semaphore(50):
        client = await _get_client()
        params = {"symbol": symbol}
        try:
            resp = await client.get(OI_API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            return {
                "symbol": symbol,
                "oi": data["openInterest"],
                "time": int(data.get("time") or data.get("timestamp")),
            }
        except Exception as exc:                     # noqa: BLE001
            logger.warning("OI API error %s: %s", symbol, exc)
            return None


async def fetch_oi_info() -> List[OIInfo]:
    """Собираем OI, но не рвём сеть и цикл.

    Получает информацию об открытом интересе для всех доступных perpetual-фьючерсов
    с ограничением одновременных запросов через семафор.

    Returns:
        List[OIInfo]: Список информации об открытом интересе для всех успешно обработанных символов.
    """
    symbols = await _get_perp_symbols()
    tasks = [_fetch_single(sym) for sym in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return [r for r in results if r]