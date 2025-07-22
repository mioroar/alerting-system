# coding: utf-8
"""
Singleton-менеджер CompositeListener’ов: API такое же, как у price/volume-менеджеров.
"""
import asyncio, asyncpg
from typing import Dict
from ..composite_listener import CompositeListener
from db.logic import get_pool

# ---------- core ----------
class CompositeListenerManager:
    def __init__(self) -> None:
        self._listeners: Dict[str, CompositeListener] = {}
        self._tasks: Dict[str, asyncio.Task] = {}

    # ——— CRUD ———
    async def add_listener(self, expression: str, user_id: int) -> CompositeListener:
        cid = str(hash(expression))
        if cid not in self._listeners:                 # создаём «листенер + таску» один раз
            lst = CompositeListener.from_expression(expression)
            self._listeners[cid] = lst
            pool: asyncpg.Pool = await get_pool()
            self._tasks[cid] = asyncio.create_task(self._runner(lst, pool))
        self._listeners[cid].add_subscriber(user_id)
        return self._listeners[cid]

    async def remove_listener(self, cid: str, user_id: int | None = None) -> None:
        """
        • если user_id передан — отписываем конкретного пользователя;  
        • если None — удаляем слушатель полностью (админ-команда).
        """
        if cid not in self._listeners:
            return
        if user_id is None:
            self._tasks[cid].cancel()
            del self._tasks[cid], self._listeners[cid]
            return
        self._listeners[cid].remove_subscriber(user_id)
        if not self._listeners[cid].subscribers:
            self._tasks[cid].cancel()
            del self._tasks[cid], self._listeners[cid]

    # ——— Helpers для UI ———
    def get_all_user_listeners(self, uid: int):
        return [l for l in self._listeners.values() if uid in l.subscribers]

    def unsubscribe_user_from_all(self, uid: int):
        for cid in list(self._listeners):
            if uid in self._listeners[cid].subscribers:
                asyncio.create_task(self.remove_listener(cid, uid))

    # ——— internal ———
    async def _runner(self, lst: CompositeListener, pool: asyncpg.Pool):
        while True:
            try:
                await lst.check_and_notify(pool)
            except Exception as exc:
                print(f"[Composite] {lst.expression} — ERROR:", exc, flush=True)
            await asyncio.sleep(lst.interval)


# ---------- lazy singleton ----------
_manager: CompositeListenerManager | None = None
async def get_composite_listener_manager() -> CompositeListenerManager:
    global _manager
    if _manager is None:
        _manager = CompositeListenerManager()
    return _manager
