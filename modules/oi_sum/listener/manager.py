from modules.manager import BaseListenerManager
from modules.oi_sum.listener.logic import OISumListener
from modules.oi_sum.config import OI_SUM_CHECK_INTERVAL_SEC


class OISumListenerManager(BaseListenerManager[OISumListener]):
    """Менеджер для OISumListener.
    
    Управляет слушателями абсолютных значений открытого интереса.
    Использует хеш-таблицу condition_id → OISumListener для быстрого доступа.
    
    Attributes:
        _listener_cls: Класс OISumListener.
        _listeners: Словарь активных слушателей.
        _tasks: Словарь фоновых задач для периодического обновления.
    """

    def __init__(self) -> None:
        """Инициализирует менеджер OI Sum слушателей."""
        super().__init__(OISumListener)

    async def add_listener(
        self, 
        params: dict, 
        user_id: int | None = None
    ) -> OISumListener:
        """Создаёт или возвращает OI Sum слушатель.

        Args:
            params: Параметры для создания слушателя:
                - direction (str): Направление сравнения ('>' или '<')
                - percent (float): Пороговое значение OI в USD
                - interval (int, optional): Интервал проверки в секундах
                - window_sec (int, optional): Длина окна расчёта
            user_id: Telegram ID пользователя для подписки (None для композитных алертов).

        Returns:
            OISumListener: Созданный или существующий слушатель.
        """
        params = params.copy()
        params.setdefault("interval", OI_SUM_CHECK_INTERVAL_SEC)
        return await super().add_listener(params, user_id)


_oi_sum_listener_manager: OISumListenerManager | None = None


async def get_oi_sum_listener_manager() -> OISumListenerManager:
    """Возвращает singleton экземпляр менеджера OI Sum слушателей.
    
    Использует ленивую инициализацию для создания единственного
    экземпляра менеджера при первом обращении.
    
    Returns:
        OISumListenerManager: Единственный экземпляр менеджера.
    """
    global _oi_sum_listener_manager
    if _oi_sum_listener_manager is None:
        _oi_sum_listener_manager = OISumListenerManager()
    return _oi_sum_listener_manager