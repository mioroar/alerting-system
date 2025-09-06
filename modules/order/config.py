from typing import Final, TypedDict, Dict, Any

# API URLs для получения данных с Binance
BINANCE_WS_URL: Final[str] = "wss://fstream.binance.com/stream"
FUTURES_EXCHANGE_INFO_URL: Final[str] = "https://fapi.binance.com/fapi/v1/exchangeInfo"

# Параметры отслеживания ордеров
ORDER_CHECK_INTERVAL_IN_SECONDS: Final[int] = 60  # Период проверки лисенера
ORDER_TRACKER_BATCH_INTERVAL: Final[int] = 5     # Интервал записи в БД
MIN_ORDER_SIZE_USD: Final[int] = 100_000          # Минимальный размер ордера для отслеживания
MAX_PRICE_DEVIATION_PERCENT: Final[float] = 10.0 # Максимальное отклонение от цены (±10%)

# Фильтр времени плотности
DENSITY_TIME_FILTER_MINUTES: Final[int] = 1  # Минимальное время жизни плотности в минутах

# Кэш данных
ORDER_CACHE_TTL_SEC: Final[int] = 300  # 5 минут
TICKER_CACHE: Dict[str, Dict[str, Any]] = {}  # Кэш текущих цен
SYMBOLS: list[str] = []

# WebSocket настройки  
GROUP_SIZE: Final[int] = 50  # Размер группы тикеров для одного WS соединения
WS_RECONNECT_INTERVAL: Final[int] = 3600  # Переподключение каждый час

class OrderDensity(TypedDict):
    """Информация о плотности ордеров на уровне цены.
    
    Attributes:
        symbol (str): Символ торговой пары.
        order_type (str): Тип ордера ("LONG" или "SHORT").
        price (float): Цена уровня.
        current_size_usd (float): Текущий размер в USD.
        max_size_usd (float): Максимальный размер за всё время в USD.
        touched (bool): Была ли плотность тронута (уменьшалась).
        reduction_usd (float): На сколько USD уменьшилась от максимума.
        percent_from_market (float): Процентное отклонение от рыночной цены.
        first_seen (int): Время первого появления уровня (Unix ms).
        last_updated (int): Время последнего обновления (Unix ms).
        is_new (bool): Является ли запись новой (для определения INSERT/UPDATE).
    """
    symbol: str
    order_type: str
    price: float
    current_size_usd: float
    max_size_usd: float
    touched: bool
    reduction_usd: float
    percent_from_market: float
    first_seen: int
    last_updated: int
    is_new: bool

class DensityDBOperation(TypedDict):
    """Операция для выполнения в БД.
    
    Attributes:
        operation (str): Тип операции ("INSERT", "UPDATE", "DELETE").
        data (OrderDensity | None): Данные для операции (None для DELETE).
        key (tuple): Ключ записи (symbol, price).
    """
    operation: str
    data: OrderDensity | None
    key: tuple[str, float]