import httpx
from typing import Final, TypedDict

EXINFO_API_URL: Final[str] = "https://fapi.binance.com/fapi/v1/exchangeInfo"
OI_API_URL:     Final[str] = "https://fapi.binance.com/fapi/v1/openInterest"


TICKER_BLACKLIST: Final[list[str]] = ["USDC", "BUSD"]
OI_HISTORY_PERIOD_SEC: Final[int] = 24 * 60 * 60
OI_CHECK_INTERVAL_SEC: Final[int] = 60
CACHE_TTL_SEC: Final[int] = 60
MAX_AGE_MS: Final[int] = 30_000

HTTP_TIMEOUT: Final[int] = 15
MAX_CONNECTIONS: Final[int] = 1000
MAX_KEEPALIVE_CONNECTIONS: Final[int] = 500
MAX_RETRIES: Final[int] = 3

class OIInfo(TypedDict):
    """Снимок открытого интереса одной пары."""
    symbol: str
    oi:     str
    time:   int

_CLIENT: httpx.AsyncClient | None = None

async def _get_client() -> httpx.AsyncClient:
    """Возвращает глобальный HTTP клиент с оптимальными настройками."""
    global _CLIENT
    if _CLIENT is None or _CLIENT.is_closed:
        _CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(HTTP_TIMEOUT),
            limits=httpx.Limits(
                max_connections=MAX_CONNECTIONS, 
                max_keepalive_connections=MAX_KEEPALIVE_CONNECTIONS
            ),
            transport=httpx.AsyncHTTPTransport(
                retries=MAX_RETRIES,
                http2=False
            ),
            headers={
                "User-Agent": "TradingBot/1.0",
                "Accept": "application/json",
                "Connection": "keep-alive"
            }
        )
    return _CLIENT

async def close_client() -> None:
    """Закрывает HTTP клиент."""
    global _CLIENT
    if _CLIENT is not None and not _CLIENT.is_closed:
        await _CLIENT.aclose()
        _CLIENT = None