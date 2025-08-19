# from typing import Final, TypedDict, Dict, Any

# # API URLs для получения данных с Binance
# BINANCE_WS_URL: Final[str] = "wss://fstream.binance.com/stream"
# FUTURES_EXCHANGE_INFO_URL: Final[str] = "https://fapi.binance.com/fapi/v1/exchangeInfo"

# # Параметры отслеживания ордеров
# ORDER_CHECK_INTERVAL_IN_SECONDS: Final[int] = 60  # Период проверки лисенера
# ORDER_TRACKER_BATCH_INTERVAL: Final[int] = 5     # Интервал записи в БД
# MIN_ORDER_SIZE_USD: Final[int] = 100_000          # Минимальный размер ордера для отслеживания
# MAX_PRICE_DEVIATION_PERCENT: Final[float] = 10.0 # Максимальное отклонение от цены (±10%)

# # Кэш данных
# ORDER_CACHE_TTL_SEC: Final[int] = 300  # 5 минут
# TICKER_CACHE: Dict[str, Dict[str, Any]] = {}  # Кэш текущих цен
# SYMBOLS: list[str] = []

# # WebSocket настройки  
# GROUP_SIZE: Final[int] = 50  # Размер группы тикеров для одного WS соединения
# WS_RECONNECT_INTERVAL: Final[int] = 3600  # Переподключение каждый час

# class OrderDensity(TypedDict):
#     """Информация о плотности ордеров на уровне цены.
    
#     Attributes:
#         symbol (str): Символ торговой пары.
#         order_type (str): Тип ордера ("LONG" или "SHORT").
#         price (float): Цена уровня.
#         size_usd (float): Размер в USD.
#         timestamp (int): Время последнего обновления (Unix ms).
#         first_seen (int): Время первого появления уровня (Unix ms).
#         percent_from_market (float): Процентное отклонение от рыночной цены.
#     """
#     symbol: str
#     order_type: str
#     price: float
#     size_usd: float
#     timestamp: int
#     first_seen: int
#     percent_from_market: float

# class OrderDensityRecord(TypedDict):
#     """Запись для вставки в базу данных order_density.
    
#     Attributes:
#         symbol (str): Символ торговой пары.
#         order_type (str): Тип ордера ("LONG" или "SHORT").
#         price (float): Цена уровня.
#         size_usd (float): Размер в USD.
#         percent_from_market (float): Процентное отклонение от рыночной цены.
#         first_seen (int): Время первого появления уровня (Unix ms).
#         duration_sec (int): Время жизни уровня в секундах.
#     """
#     symbol: str
#     order_type: str
#     price: float
#     size_usd: float
#     percent_from_market: float
#     first_seen: int
#     duration_sec: int