
from typing import Final, Literal, TypedDict

VOLUME_API_URL = "https://fapi.binance.com/fapi/v1/klines"
EXINFO_API_URL: Final[str] = "https://fapi.binance.com/fapi/v1/exchangeInfo"
_STREAM_URL: Final[str] = "wss://fstream.binance.com/stream"

TICKER_BLACKLIST = ["USDC", "BUSD"]

_FLUSH_INTERVAL_SEC: Final[int] = 5
VOLUME_CHECK_INTERVAL_IN_SECONDS = 60
_CACHE_TTL_SEC: Final[int] = 60 
MAX_AGE_MS = 30_000

class VolumeInfo(TypedDict):
    symbol: str
    volume: str
    time: int

class _ExSymbol(TypedDict):
    symbol: str
    status: Literal["TRADING", "BREAK", "SETTLING", "CLOSE"]
    contractType: str

