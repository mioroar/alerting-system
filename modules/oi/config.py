import httpx
from typing import Final, TypedDict

EXINFO_API_URL: Final[str] = "https://fapi.binance.com/fapi/v1/exchangeInfo"
OI_API_URL:     Final[str] = "https://fapi.binance.com/fapi/v1/openInterest"


TICKER_BLACKLIST: Final[list[str]] = ["USDC", "BUSD"]
OI_HISTORY_PERIOD_SEC: Final[int] = 24 * 60 * 60
OI_CHECK_INTERVAL_SEC: Final[int] = 60
CACHE_TTL_SEC: Final[int] = 60
MAX_AGE_MS: Final[int] = 30_000

class OIInfo(TypedDict):
    """Снимок открытого интереса одной пары."""
    symbol: str
    oi:     str
    time:   int

_CLIENT: httpx.AsyncClient | None = None

async def _get_client() -> httpx.AsyncClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = httpx.AsyncClient(
            timeout=10,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=50),
        )
    return _CLIENT