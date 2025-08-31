from typing import Final, TypedDict

# API endpoints
KLINES_API_URL: Final[str] = "https://fapi.binance.com/fapi/v1/klines"
EXCHANGE_INFO_API_URL: Final[str] = "https://fapi.binance.com/fapi/v1/exchangeInfo"

# Интервалы
ORDER_NUM_CHECK_INTERVAL_SEC: Final[int] = 60  # Частота сбора данных (1 минута)
ORDER_NUM_DEFAULT_WINDOW_SEC: Final[int] = 600  # Окно по умолчанию (10 минут)
KLINE_INTERVAL: Final[str] = "1m"  # Интервал свечей

# Лимиты API
MAX_KLINES_PER_REQUEST: Final[int] = 500  # Максимум свечей за запрос
CONCURRENT_REQUESTS: Final[int] = 10  # Параллельные запросы
RATE_LIMIT_PER_MINUTE: Final[int] = 1200  # Лимит запросов в минуту

# HTTP настройки
HTTP_TIMEOUT: Final[int] = 10
MAX_RETRIES: Final[int] = 3


class TradeCountInfo(TypedDict):
    """Информация о количестве сделок."""
    symbol: str
    trade_count: int
    time: int  # Unix timestamp в миллисекундах