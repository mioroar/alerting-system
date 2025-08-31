from modules.manager import BaseListenerManager
from modules.order_num.listener.logic import OrderNumListener
from modules.order_num.config import ORDER_NUM_CHECK_INTERVAL_SEC


class OrderNumListenerManager(BaseListenerManager[OrderNumListener]):
    """Менеджер для OrderNumListener.
    
    Управляет слушателями изменения количества сделок.
    
    Attributes:
        _listener_cls: Класс OrderNumListener.
        _listeners: Словарь активных слушателей.
        _tasks: Словарь фоновых задач.
    """

    def __init__(self) -> None:
        """Инициализирует менеджер слушателей количества сделок."""
        super().__init__(OrderNumListener)

    async def add_listener(
        self, 
        params: dict, 
        user_id: int | None = None
    ) -> OrderNumListener:
        """Создаёт или возвращает слушатель количества сделок.

        Args:
            params: Параметры слушателя:
                - direction (str): Направление сравнения ('>' или '<')
                - percent (float): Процент изменения
                - window_sec (int): Размер окна в секундах
                - interval (int, optional): Интервал проверки
            user_id: Telegram ID пользователя (None для композитных).

        Returns:
            OrderNumListener: Созданный или существующий слушатель.
        """
        params = params.copy()
        params.setdefault("interval", ORDER_NUM_CHECK_INTERVAL_SEC)
        return await super().add_listener(params, user_id)


# Singleton экземпляр
_order_num_listener_manager: OrderNumListenerManager | None = None


async def get_order_num_listener_manager() -> OrderNumListenerManager:
    """Возвращает singleton экземпляр менеджера.
    
    Returns:
        OrderNumListenerManager: Единственный экземпляр менеджера.
    """
    global _order_num_listener_manager
    if _order_num_listener_manager is None:
        _order_num_listener_manager = OrderNumListenerManager()
    return _order_num_listener_manager