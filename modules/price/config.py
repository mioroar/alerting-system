from typing import Final, Literal, TypedDict

PRICE_API_URL = "https://fapi.binance.com/fapi/v1/ticker/price"
EXINFO_API_URL: Final[str] = "https://fapi.binance.com/fapi/v1/exchangeInfo"

TICKER_BLACKLIST = ["USDC", "BUSD"]

PRICE_CHECK_INTERVAL_IN_SECONDS = 10
_CACHE_TTL_SEC: Final[int] = 60 
MAX_AGE_MS = 30_000

class PriceInfo(TypedDict):
    symbol: str
    price: str
    time: int

class _ExSymbol(TypedDict):
    symbol: str
    status: Literal["TRADING", "BREAK", "SETTLING", "CLOSE"]
    contractType: str