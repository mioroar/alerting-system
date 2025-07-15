import asyncio
import asyncpg
from typing import Dict, List


from modules.price.listener.logic import Listener
from db.logic import get_pool

class ListenerManager:
    """Управляет жизненным циклом объектов Listener

    Каждый Listener идентифицируется condition_id, вычисляемым из параметров
    условия (процент и интервал). Один Listener может иметь множество
    подписчиков, поэтому повторное добавление условия с теми же
    параметрами только расширяет существующий список подписчиков.

    Attributes:
        listeners (Dict[str, Listener]): Активные Listener, индексированные
            по condition_id.
        tasks (Dict[str, asyncio.Task]): Задачи, периодически вызывающие
            Listener.check_and_notify.
    """
    def __init__(self):
        self.listeners: Dict[str, Listener] = {}
        self.tasks: Dict[str, asyncio.Task] = {}
        
    def get_condition_id(self, params: dict) -> str:
        """Возвращает идентификатор условия.

        Args:
            params (dict): Словарь с ключами percent и interval.

        Returns:
            str: Строковый хеш‑идентификатор, однозначно определяющий пару
                (percent, interval).
        """
        return str(hash((params["percent"], params["interval"])))
    
    async def _run_listener_periodically(self, listener: Listener, db_pool: asyncpg.Pool) -> None:
        """Бесконечно вызывает listener.check_and_notify с задержкой.

        Args:
            listener (Listener): Экземпляр слушателя, для которого запускается
                цикл проверок.
            db_pool (asyncpg.Pool): Пул соединений к PostgreSQL.
        """
        while True:
            await listener.check_and_notify(db_pool)
            await asyncio.sleep(listener.interval)
    
    async def add_listener(self, params: dict, user_id: int) -> Listener:
        """Регистрирует пользователя на получение уведомлений.

        Если Listener с заданными параметрами не существует, он создаётся и
        запускается фоновая задача. В противном случае пользователь лишь
        добавляется в список подписчиков.

        Args:
            params (dict): Параметры условия (ключи percent, interval).
            user_id (int): Telegram‑ID подписчика.

        Returns:
            Listener: Экземпляр, на который был подписан пользователь.
        """
        condition_id = self.get_condition_id(params)
        if condition_id not in self.listeners:
            listener = Listener(condition_id,
                                params["percent"],
                                params["interval"])
            self.listeners[condition_id] = listener
            db_pool = await get_pool()
            self.tasks[condition_id] = asyncio.create_task(
                self._run_listener_periodically(
                    listener, db_pool
                )
            )
        if user_id not in self.listeners[condition_id].subscribers:
            self.listeners[condition_id].add_subscriber(user_id)
        return self.listeners[condition_id]
    
    async def remove_listener(self, condition_id: str) -> None:
        """Полностью останавливает Listener и освобождает ресурсы.

        Args:
            condition_id (str): Идентификатор условия, возвращаемый
                get_condition_id.
        """
        if condition_id in self.listeners:
            if condition_id in self.tasks:
                self.tasks[condition_id].cancel()
            del self.listeners[condition_id]
            self.tasks.pop(condition_id, None)

    async def remove_subscriber(self, condition_id: str, user_id: int) -> None:
        """Отписывает пользователя и удаляет Listener при отсутствии подписчиков.

        Args:
            condition_id (str): Идентификатор условия.
            user_id (int): Telegram‑ID подписчика.
        """
        if condition_id in self.listeners:
            listener = self.listeners[condition_id]
            listener.remove_subscriber(user_id)
            if not listener.subscribers:
                await self.remove_listener(condition_id)

    def get_all_user_listeners(self, user_id: int) -> List[Listener]:
        """Возвращает все Listener, на которые подписан пользователь.

        Args:
            user_id (int): Telegram‑ID пользователя.

        Returns:
            List[Listener]: Список Listener, на которые подписан пользователь.
        """
        return [listener for listener in self.listeners.values() if user_id in listener.subscribers]
    
    def unsubscribe_user_from_all_listeners(self, user_id: int) -> None:
        """Отписывает пользователя от всех Listener.

        Args:
            user_id (int): Telegram‑ID пользователя.
        """
        for listener in self.listeners.values():
            if user_id in listener.subscribers:
                listener.remove_subscriber(user_id)

listener_manager = ListenerManager()

async def get_listener_manager() -> ListenerManager:
    """Возвращает (и при необходимости создаёт) глобальный ListenerManager.

    Returns:
        ListenerManager: Глобальный экземпляр менеджера.
    """
    global listener_manager
    if listener_manager is None:
        listener_manager = ListenerManager()
    return listener_manager