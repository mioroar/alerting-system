from __future__ import annotations

import asyncio
import asyncpg
from typing import Dict, List

from db.logic import get_pool
from modules.volume.listener.logic import VolumeAmountListener


class VolumeAmountListenerManager:
    """Менеджер для управления слушателями объёма торгов.

    Singleton-класс, который создаёт, хранит и удаляет экземпляры VolumeAmountListener.
    Обеспечивает переиспользование слушателей с одинаковыми параметрами и управление
    подписками пользователей.

    Attributes:
        _listeners: Словарь активных слушателей по их condition_id.
        _tasks: Словарь асинхронных задач для каждого слушателя.
    """

    def __init__(self) -> None:
        """Инициализирует менеджер слушателей.

        Создаёт пустые словари для хранения слушателей и их задач.
        """
        self._listeners: Dict[str, VolumeAmountListener] = {}
        self._tasks: Dict[str, asyncio.Task] = {}

    def get_condition_id(self, params: dict) -> str:
        """Генерирует уникальный идентификатор условия на основе параметров.

        Args:
            params: Словарь с параметрами условия. Должен содержать ключи:
                   'amount', 'interval', 'direction'.

        Returns:
            Строковое представление хеша от параметров условия.
        """
        return str(hash((params["amount"], params["interval"], params["direction"])))

    async def add_listener(self, params: dict, user_id: int) -> VolumeAmountListener:
        """Добавляет или возвращает существующий слушатель и подписывает пользователя.

        Если слушатель с такими параметрами уже существует, подписывает пользователя
        на существующий. Иначе создаёт новый слушатель и запускает его в отдельной задаче.

        Args:
            params: Словарь параметров для слушателя. Должен содержать:
                   'amount', 'interval', 'direction'.
            user_id: Идентификатор пользователя для подписки.

        Returns:
            Экземпляр VolumeAmountListener, на который подписан пользователь.
        """
        cid = self.get_condition_id(params)

        if cid not in self._listeners:
            listener = VolumeAmountListener(
                cid,
                amount=params["amount"],
                interval=params["interval"],
                direction=params["direction"],
            )
            self._listeners[cid] = listener

            db_pool: asyncpg.Pool = await get_pool()
            self._tasks[cid] = asyncio.create_task(
                self._run_listener_periodically(listener, db_pool)
            )

        self._listeners[cid].add_subscriber(user_id)
        return self._listeners[cid]

    async def remove_listener(self, condition_id: str) -> None:
        """Полностью останавливает и удаляет слушатель.

        Отменяет асинхронную задачу слушателя и удаляет его из всех словарей.
        Используется при явной отписке всех пользователей.

        Args:
            condition_id: Идентификатор условия слушателя для удаления.
        """
        if condition_id in self._tasks:
            self._tasks[condition_id].cancel()
            del self._tasks[condition_id]
        self._listeners.pop(condition_id, None)

    def get_all_user_listeners(self, user_id: int) -> List[VolumeAmountListener]:
        """Возвращает все слушатели, на которые подписан пользователь.

        Args:
            user_id: Идентификатор пользователя.

        Returns:
            Список экземпляров VolumeAmountListener, где пользователь является подписчиком.
        """
        return [lst for lst in self._listeners.values() if user_id in lst.subscribers]

    def unsubscribe_user_from_all(self, user_id: int) -> None:
        """Отписывает пользователя от всех слушателей без их удаления.

        Удаляет пользователя из списка подписчиков всех активных слушателей,
        но не останавливает сами слушатели.

        Args:
            user_id: Идентификатор пользователя для отписки.
        """
        for lst in self._listeners.values():
            lst.remove_subscriber(user_id)

    async def _run_listener_periodically(
        self, listener: VolumeAmountListener, db_pool: asyncpg.Pool
    ) -> None:
        """Запускает периодическую проверку условий слушателя.

        Бесконечно вызывает метод check_and_notify слушателя с интервалом,
        заданным в настройках слушателя.

        Args:
            listener: Экземпляр слушателя для периодического запуска.
            db_pool: Пул соединений с базой данных.
        """
        while True:
            await listener.check_and_notify(db_pool)
            await asyncio.sleep(listener.interval)


volume_amount_listener_manager = VolumeAmountListenerManager()


async def get_volume_amount_listener_manager() -> VolumeAmountListenerManager:
    """Возвращает экземпляр синглтона менеджера слушателей объёма.

    Returns:
        Глобальный экземпляр VolumeAmountListenerManager.
    """
    return volume_amount_listener_manager
