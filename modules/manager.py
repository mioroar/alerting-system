import asyncio
import asyncpg
from typing import Dict, Generic, List, Type, TypeVar

from config import logger
from db.logic import get_pool
from modules.listener import Listener


WhatListener = TypeVar("WhatListener", bound=Listener)


class BaseListenerManager(Generic[WhatListener]):
    """Общий менеджер для любых Listener‑подобных классов.

    Args:
        listener_cls: Класс, экземпляры которого будет создавать менеджер.
    """

    def __init__(self, listener_cls: Type[WhatListener]) -> None:
        self._listener_cls: Type[WhatListener] = listener_cls
        self._listeners: Dict[str, WhatListener] = {}
        self._tasks: Dict[str, asyncio.Task] = {}

    def get_condition_id(self, params: dict) -> str:
        """Генерирует уникальный ID условия.

        Хешируются *direction*, *percent/amount* и *interval*.

        Args:
            params: Параметры, передаваемые при создании слушателя.

        Returns:
            Строковый идентификатор.
        """
        key = (params["direction"], params["percent"], params["interval"])
        return str(hash(key))

    async def add_listener(self, params: dict, user_id: int) -> WhatListener:
        """Создаёт/возвращает слушатель и подписывает пользователя."""
        cid = self.get_condition_id(params)

        if cid not in self._listeners:
            listener = self._listener_cls(
                cid,
                direction=params["direction"],
                percent=params["percent"],
                interval=params["interval"],
            )
            self._listeners[cid] = listener

            db_pool = await get_pool()
            self._tasks[cid] = asyncio.create_task(
                self._run_listener_periodically(listener, db_pool)
            )

        self._listeners[cid].add_subscriber(user_id)
        return self._listeners[cid]

    async def remove_subscriber(self, condition_id: str, user_id: int) -> None:
        """Отписывает пользователя; удаляет слушатель, если подписчиков не осталось."""
        listener = self._listeners.get(condition_id)
        if listener is None:
            return

        listener.remove_subscriber(user_id)
        if not listener.subscribers:
            await self.remove_listener(condition_id)

    async def remove_listener(self, condition_id: str) -> None:
        """Полностью останавливает и удаляет слушатель."""
        if condition_id in self._tasks:
            self._tasks[condition_id].cancel()
            del self._tasks[condition_id]
        self._listeners.pop(condition_id, None)

    def get_all_user_listeners(self, user_id: int) -> List[WhatListener]:
        """Возвращает все слушатели, на которые подписан пользователь."""
        return [l for l in self._listeners.values() if user_id in l.subscribers]

    def unsubscribe_user_from_all(self, user_id: int) -> None:
        """Отписывает пользователя от всех слушателей (без их удаления)."""
        for listener in self._listeners.values():
            listener.remove_subscriber(user_id)

    async def _run_listener_periodically(
        self, listener: WhatListener, db_pool: asyncpg.Pool
    ) -> None:
        """Фоновая корутина: update_state → notify с интервалом listener.interval."""
        while True:
            try:
                await listener.update_state(db_pool)
                await listener.notify()
            except Exception as exc:
                logger.error("Listener %s error: %s", listener.condition_id, exc)
            finally:
                await asyncio.sleep(listener.interval)
