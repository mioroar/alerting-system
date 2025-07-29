import time
import httpx
from typing import List

from config import logger
from modules.funding.config import BINANCE_FUNDING_URL, FundingInfo


async def fetch_funding_info() -> List[FundingInfo]:
    """Асинхронно запрашивает funding-ставки всех perp-пар Binance.

    Исключает пары с «USDC» (они неинтересны) и конвертирует к типу FundingInfo.

    Returns:
        List[FundingInfo]: Список информации о funding ставках.

    Raises:
        httpx.TimeoutException: При превышении времени ожидания запроса.
        httpx.HTTPStatusError: При ошибке HTTP статуса от API.
        httpx.RequestError: При ошибке сетевого запроса.
        Exception: При неожиданных ошибках.

    Note:
        Исключает пары с «USDC» из результатов.
    """
    try:
        async with httpx.AsyncClient(timeout=30) as client:  # Увеличил timeout
            resp = await client.get(BINANCE_FUNDING_URL)
            resp.raise_for_status()
            raw = resp.json()
    except httpx.TimeoutException as e:
        logger.error("Binance API timeout: %s", e)
        raise
    except httpx.HTTPStatusError as e:
        logger.error("Binance API HTTP error %s: %s", e.response.status_code, e.response.text)
        raise
    except httpx.RequestError as e:
        logger.error("Binance API request error: %s", e)
        raise
    except Exception as e:
        logger.error("Unexpected error fetching funding data: %s", e)
        raise

    if not isinstance(raw, list):
        logger.error("Expected list from Binance API, got: %s", type(raw))
        return []

    now_ms = int(time.time() * 1000)
    items: List[FundingInfo] = []
    
    for item in raw:
        try:
            symbol = item.get("symbol", "")
            if not symbol:
                logger.warning("Empty symbol in funding data: %s", item)
                continue
                
            if "usdc" in symbol.lower():
                continue
            
            # Проверяем обязательные поля
            rate = item.get("lastFundingRate")
            next_funding_time = item.get("nextFundingTime")
            
            if rate is None or next_funding_time is None:
                logger.warning("Missing required fields for %s: rate=%s, next_funding_time=%s", 
                             symbol, rate, next_funding_time)
                continue
            
            items.append({
                "symbol": symbol,
                "rate": str(rate),  # Приводим к строке явно
                "next_funding_ts": int(next_funding_time),
                "time": now_ms,
            })
            
        except (ValueError, TypeError) as e:
            logger.warning("Error processing funding item %s: %s", item, e)
            continue

    logger.debug("Fetched %d funding items", len(items))
    return items