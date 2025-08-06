import httpx
import asyncio
import time
from typing import List, Set

from modules.oi.config import EXINFO_API_URL, OI_API_URL, OIInfo, _get_client
from modules.config import TICKER_BLACKLIST
from config import logger

_FAILED_SYMBOLS: Set[str] = set()
_FAILED_SYMBOLS_TTL: dict[str, float] = {}
_CACHE_DURATION = 3600

def _is_symbol_blacklisted(symbol: str) -> bool:
    """Проверяет, находится ли символ в черном списке.

    Args:
        symbol: Символ торговой пары для проверки.

    Returns:
        bool: True если символ в черном списке, False иначе.

    Raises:
        None
    """
    current_time = time.time()
    
    expired_symbols = [
        sym for sym, expire_time in _FAILED_SYMBOLS_TTL.items()
        if current_time > expire_time
    ]
    for sym in expired_symbols:
        _FAILED_SYMBOLS.discard(sym)
        _FAILED_SYMBOLS_TTL.pop(sym, None)
    
    return symbol in _FAILED_SYMBOLS

def _add_to_blacklist(symbol: str) -> None:
    """Добавляет символ в черный список на определенное время.

    Args:
        symbol: Символ торговой пары для добавления в черный список.

    Returns:
        None

    Raises:
        None

    Note:
        Символ остается в черном списке на время _CACHE_DURATION секунд.
    """
    _FAILED_SYMBOLS.add(symbol)
    _FAILED_SYMBOLS_TTL[symbol] = time.time() + _CACHE_DURATION
    logger.debug("Added %s to temporary blacklist", symbol)

async def _get_perp_symbols() -> list[str]:
    """Возвращает список символов perpetual-фьючерсов Binance.

    Исключает пары из ``TICKER_BLACKLIST`` и временно проблемные символы.

    Returns:
        list[str]: Список символов perpetual-фьючерсов, доступных для торговли.

    Raises:
        Exception: При ошибке получения данных с Binance API.

    Note:
        Исключает символы, которые находятся в черном списке или не торгуются.
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(EXINFO_API_URL)
            resp.raise_for_status()
            data = resp.json()
            
            symbols = []
            for s in data.get("symbols", []):
                symbol = s.get("symbol", "")
                
                if (s.get("contractType") != "PERPETUAL" or 
                    s.get("status") != "TRADING" or
                    any(blk.lower() in symbol.lower() for blk in TICKER_BLACKLIST)):
                    continue
                
                if _is_symbol_blacklisted(symbol):
                    continue
                
                symbols.append(symbol)
                
        logger.debug("Found %d active perpetual symbols", len(symbols))
        return symbols
        
    except Exception as exc:
        logger.exception("Error fetching exchange info: %s", exc)
        return []

async def _fetch_single(symbol: str) -> OIInfo | None:
    """Получить OI для одного символа.

    Args:
        symbol: Символ торговой пары для получения данных OI.

    Returns:
        OIInfo | None: Информация об открытом интересе для символа или None в случае ошибки.

    Raises:
        httpx.HTTPStatusError: При ошибке HTTP статуса от API.
        httpx.TimeoutException: При превышении времени ожидания запроса.
        httpx.RequestError: При ошибке сетевого запроса.
        Exception: При неожиданных ошибках обработки данных.
    """
    if _is_symbol_blacklisted(symbol):
        return None
        
    async with asyncio.Semaphore(50):
        client = await _get_client()
        params = {"symbol": symbol}
        
        try:
            resp = await client.get(OI_API_URL, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            if "openInterest" not in data:
                logger.warning("Missing openInterest field for %s", symbol)
                return None
                
            return {
                "symbol": symbol,
                "oi": str(data["openInterest"]),
                "time": int(data.get("time") or data.get("timestamp") or time.time() * 1000),
            }
            
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (400, 404):
                _add_to_blacklist(symbol)
                logger.warning("Symbol %s not available (HTTP %d), blacklisted temporarily", 
                             symbol, exc.response.status_code)
            else:
                logger.warning("OI API HTTP error %s (%d): %s", 
                             symbol, exc.response.status_code, exc.response.text[:200])
            return None
            
        except httpx.TimeoutException:
            logger.warning("OI API timeout for %s", symbol)
            return None
            
        except httpx.RequestError as exc:
            logger.warning("OI API request error %s: %s", symbol, exc)
            return None
            
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("OI API data error %s: %s", symbol, exc)
            return None
            
        except Exception as exc:
            logger.warning("OI API unexpected error %s: %s", symbol, exc)
            return None

async def fetch_oi_info() -> List[OIInfo]:
    """Собираем OI, но не рвём сеть и цикл.

    Получает информацию об открытом интересе для всех доступных perpetual-фьючерсов
    с ограничением одновременных запросов через семафор.

    Returns:
        List[OIInfo]: Список информации об открытом интересе для всех успешно обработанных символов.

    Raises:
        Exception: При критических ошибках в процессе сбора данных.

    Note:
        Использует семафор для ограничения одновременных запросов (максимум 50).
        Автоматически добавляет проблемные символы в черный список.
    """
    symbols = await _get_perp_symbols()
    
    if not symbols:
        logger.warning("No symbols available for OI collection")
        return []
    
    logger.debug("Fetching OI for %d symbols", len(symbols))
    
    tasks = [_fetch_single(sym) for sym in symbols]
    
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful_results = []
        error_count = 0
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                error_count += 1
                logger.debug("Task failed for symbol %s: %s", symbols[i], result)
            elif result is not None:
                successful_results.append(result)
        
        if error_count > 0:
            logger.info("OI collection completed: %d successful, %d failed, %d blacklisted", 
                       len(successful_results), error_count, len(_FAILED_SYMBOLS))
        
        return successful_results
        
    except Exception as exc:
        logger.exception("Critical error in fetch_oi_info: %s", exc)
        return []

def get_blacklist_stats() -> dict:
    """Возвращает статистику черного списка для мониторинга.

    Returns:
        dict: Словарь со статистикой черного списка:
            - blacklisted_count: Количество активных символов в черном списке
            - blacklisted_symbols: Список активных символов в черном списке
            - cache_duration_sec: Длительность кэширования в секундах

    Raises:
        None
    """
    current_time = time.time()
    active_blacklist = [
        sym for sym, expire_time in _FAILED_SYMBOLS_TTL.items()
        if current_time <= expire_time
    ]
    
    return {
        "blacklisted_count": len(active_blacklist),
        "blacklisted_symbols": active_blacklist,
        "cache_duration_sec": _CACHE_DURATION
    }