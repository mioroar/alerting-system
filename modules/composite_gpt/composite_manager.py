import asyncio, asyncpg
from typing import Dict

from db.logic import get_pool

from .composite_listener import CompositeListener


class CompositeListenerManager:
    def __init__(self):
        self._listeners: Dict[str, CompositeListener] = {}
        self._tasks: Dict[str, asyncio.Task] = {}

    async def add_listener(self, expression: str, user_id: int) -> CompositeListener:
        cid = str(hash(expression))
        if cid not in self._listeners:
            lst = CompositeListener.from_expression(expression)
            self._listeners[cid] = lst
            db_pool: asyncpg.Pool = await get_pool()
            self._tasks[cid] = asyncio.create_task(
                self._run_periodically(lst, db_pool)
            )
        self._listeners[cid].add_subscriber(user_id)
        return self._listeners[cid]

    async def _run_periodically(self, lst: CompositeListener, pool: asyncpg.Pool) -> None:
        while True:
            await lst.check_and_notify(pool)
            await asyncio.sleep(lst.interval)

    async def remove_subscriber(self, cid: str, user_id: int) -> None:
        if cid in self._listeners:
            self._listeners[cid].remove_subscriber(user_id)
            if not self._listeners[cid].subscribers:   # авто-отключение, если никому не нужно
                self._tasks[cid].cancel()
                del self._tasks[cid]
                del self._listeners[cid]


composite_listener_manager = CompositeListenerManager()
