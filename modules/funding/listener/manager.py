import asyncio

from db.logic import get_pool
from modules.manager import BaseListenerManager
from modules.funding.listener.logic import FundingListener
from modules.funding.config import FIXED_LISTENER_INTERVAL_SEC


class FundingListenerManager(BaseListenerManager[FundingListener]):
    """Менеджер для управления FundingListener объектами.

    Attributes:
        _listeners: Словарь condition_id → FundingListener.
        _tasks: Словарь condition_id → asyncio.Task.
    """

    def __init__(self) -> None:
        """Инициализирует FundingListenerManager.

        Returns:
            None
        """
        super().__init__(FundingListener)

    async def add_listener(self, params: dict, user_id: int) -> FundingListener:
        """Создать/получить слушатель с обязательным `time_threshold_sec`.

        Args:
            params: Словарь с параметрами слушателя.
                Обязательные ключи:
                - direction: Направление сравнения ("<" или ">").
                - percent: Пороговое значение в процентах.
                - time_threshold_sec: Максимальное время до расчёта в секундах.
            user_id: ID пользователя для подписки.

        Returns:
            FundingListener: Созданный или существующий слушатель.

        Raises:
            KeyError: При отсутствии обязательных параметров в params.
            ValueError: При неверных значениях параметров.
        """
        params = params.copy()
        params["interval"] = FIXED_LISTENER_INTERVAL_SEC  # опрос раз/мин

        cid = self._make_condition_id(params)

        listener = self._listeners.get(cid)
        if listener is None:
            listener = FundingListener(
                condition_id=cid,
                direction=params["direction"],
                percent=params["percent"],
                time_threshold_sec=params["time_threshold_sec"],
                interval=params["interval"],
            )
            self._listeners[cid] = listener
            

            db_pool = await get_pool()
            self._tasks[cid] = asyncio.create_task(
                self._run_listener_periodically(listener, db_pool)
            )

        listener.add_subscriber(user_id)
        return listener
    
    @staticmethod
    def _make_condition_id(params: dict) -> str:
        """Хэшируем ключевые поля, чтобы получить детерминированный ID.

        Args:
            params: Словарь с параметрами слушателя.

        Returns:
            str: Детерминированный ID на основе ключевых параметров.

        Raises:
            KeyError: При отсутствии обязательных ключей в params.
        """
        key = (
            params["direction"],
            params["percent"],
            params["time_threshold_sec"],
        )
        return str(hash(key))



_manager: FundingListenerManager | None = None


async def get_funding_listener_manager() -> FundingListenerManager:
    """Ленивый singleton-фабричный метод.

    Returns:
        FundingListenerManager: Единственный экземпляр менеджера.

    Raises:
        None
    """
    global _manager
    if _manager is None:
        _manager = FundingListenerManager()
    return _manager
