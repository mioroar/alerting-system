import asyncio
import asyncpg
from typing import Dict, List


from modules.price.listener.logic import Listener
from db.logic import get_pool

class ListenerManager:
    def __init__(self):
        self.listeners: Dict[str, Listener] = {}
        self.tasks: Dict[str, asyncio.Task] = {}
        
    def get_condition_id(self, params: dict) -> str:
        """Теперь формируем ID **без** тикера."""
        return str(hash((params["percent"], params["interval"])))
    
    async def _run_listener_periodically(self, listener: Listener, db_pool: asyncpg.Pool) -> None:
        """
        Запускает проверку listener.check_and_notify с заданным интервалом.

        Args:
        listener (Listener): Экземпляр Listener.
        db_pool (asyncpg.Pool): Пул соединений с БД.
        interval (int): Интервал между проверками в секундах.
        """
        while True:
            await listener.check_and_notify(db_pool)
            await asyncio.sleep(listener.interval)
    
    async def add_listener(self, params: dict, user_id: int) -> Listener:
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
        if condition_id in self.listeners:
            if condition_id in self.tasks:
                self.tasks[condition_id].cancel()
            del self.listeners[condition_id]
            self.tasks.pop(condition_id, None)

    async def remove_subscriber(self, condition_id: str, user_id: int) -> None:
        if condition_id in self.listeners:
            listener = self.listeners[condition_id]
            listener.remove_subscriber(user_id)
            if not listener.subscribers:
                await self.remove_listener(condition_id)

    def get_all_user_listeners(self, user_id: int) -> List[Listener]:
        return [listener for listener in self.listeners.values() if user_id in listener.subscribers]
    
    def unsubscribe_user_from_all_listeners(self, user_id: int) -> None:
        for listener in self.listeners.values():
            listener.remove_subscriber(user_id)

listener_manager = ListenerManager()

async def get_listener_manager() -> ListenerManager:
    global listener_manager
    if listener_manager is None:
        listener_manager = ListenerManager()
    return listener_manager