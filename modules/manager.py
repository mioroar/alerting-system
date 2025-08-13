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
        key_fields = ["direction"]
        
        for field in ["percent", "amount_usd", "time_threshold_sec"]:
            if field in params:
                key_fields.append((field, params[field]))
                break
        
        if "interval" in params:
            key_fields.append(("interval", params["interval"]))
        if "window_sec" in params:
            key_fields.append(("window_sec", params["window_sec"]))
        
        return str(hash(tuple(key_fields)))

    async def add_listener(
            self,
            params: dict,
            user_id: int | None = None,
    ) -> WhatListener:
        """Возвращает (либо создаёт) слушатель с заданными параметрами.

        Если `user_id` указан, добавляет его в подписчики слушателя.
        При `user_id is None` подписка пропускается – это нужно
        композитным алертам, где уведомления идут через общий слой.

        Args:
            params: Словарь параметров, специфичный для модуля.
                Обязательные ключи: "direction", "percent", "interval".
                опционально: window_sec (int) — длина окна в секундах
            user_id: Telegram ID подписчика или None.

        Returns:
            WhatListener: Готовый объект‑слушатель (существующий или новый).
        """
        cid = self.get_condition_id(params)

        if cid not in self._listeners:
            listener = self._listener_cls(
                cid,
                direction=params["direction"],
                percent=params["percent"],
                interval=params["interval"],
                window_sec=int(params.get("window_sec", params["interval"])),
            )
            self._listeners[cid] = listener

            db_pool = await get_pool()
            self._tasks[cid] = asyncio.create_task(
                self._run_listener_periodically(listener, db_pool)
            )

        if user_id is not None:
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
                logger.exception("Listener %s error: %s", listener.condition_id, exc)
            finally:
                await asyncio.sleep(listener.interval)
