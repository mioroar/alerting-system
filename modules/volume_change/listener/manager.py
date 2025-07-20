import asyncio
import asyncpg
from typing import Dict, List

from db.logic import get_pool
from modules.volume_change.listener.logic import VolumeChangeListener


class VolumeChangeListenerManager:
    """Управляет жизненным циклом VolumeListener объектов и их фоновых задач.
    
    Класс отвечает за создание, хранение и удаление слушателей объёма торгов,
    а также управление соответствующими асинхронными задачами мониторинга.
    Реализует паттерн Singleton для централизованного управления слушателями.
    
    Attributes:
        _listeners (Dict[str, VolumeListener]): Словарь активных слушателей по их ID.
        _tasks (Dict[str, asyncio.Task]): Словарь фоновых задач по ID слушателей.
    """

    def __init__(self) -> None:
        """Инициализирует менеджер с пустыми коллекциями слушателей и задач."""
        self._listeners: Dict[str, VolumeChangeListener] = {}
        self._tasks: Dict[str, asyncio.Task] = {}

    def get_condition_id(self, params: dict) -> str:
        """Генерирует уникальный идентификатор условия на основе параметров.
        
        Создаёт хеш на основе процента изменения, интервала и направления для использования
        в качестве ключа кэширования слушателей.
        
        Args:
            params (dict): Словарь с параметрами условия, должен содержать 
                         ключи 'percent', 'interval' и 'direction'.
                         
        Returns:
            str: Строковое представление хеша пары (percent, interval, direction).
        """
        return str(hash((params["percent"], params["interval"], params["direction"])))

    async def add_listener(self, params: dict, user_id: int) -> VolumeChangeListener:
        """Создаёт или находит существующий слушатель и подписывает пользователя.
        
        Если слушатель с данными параметрами уже существует, добавляет пользователя
        в подписчики. Иначе создаёт новый слушатель и запускает для него фоновую задачу.
        
        Args:
            params (dict): Параметры условия, содержащие 'percent' и 'interval'.
            user_id (int): Идентификатор пользователя для подписки.
            
        Returns:
            VolumeListener: Экземпляр слушателя (новый или существующий).
        """
        cid = self.get_condition_id(params)

        if cid not in self._listeners:
            listener = VolumeChangeListener(cid, params["percent"], params["interval"], params["direction"])
            self._listeners[cid] = listener

            db_pool: asyncpg.Pool = await get_pool()
            self._tasks[cid] = asyncio.create_task(
                self._run_listener_periodically(listener, db_pool)
            )

        self._listeners[cid].add_subscriber(user_id)
        return self._listeners[cid]

    async def remove_subscriber(self, condition_id: str, user_id: int) -> None:
        """Отписывает пользователя от слушателя и удаляет слушатель при необходимости.
        
        Удаляет пользователя из списка подписчиков указанного слушателя.
        Если после удаления у слушателя не остаётся подписчиков, полностью
        останавливает и удаляет слушатель.
        
        Args:
            condition_id (str): Уникальный идентификатор условия.
            user_id (int): Идентификатор пользователя для отписки.
        """
        listener = self._listeners.get(condition_id)
        if not listener:
            return

        listener.remove_subscriber(user_id)
        if not listener.subscribers:
            await self.remove_listener(condition_id)

    async def remove_listener(self, condition_id: str) -> None:
        """Полностью останавливает слушатель и освобождает связанные ресурсы.
        
        Отменяет фоновую задачу слушателя и удаляет его из внутренних коллекций.
        
        Args:
            condition_id (str): Уникальный идентификатор условия для удаления.
        """
        if condition_id in self._tasks:
            self._tasks[condition_id].cancel()
            del self._tasks[condition_id]
        self._listeners.pop(condition_id, None)

    def get_all_user_listeners(self, user_id: int) -> List[VolumeChangeListener]:
        """Возвращает список всех слушателей, на которые подписан пользователь.
        
        Args:
            user_id (int): Идентификатор пользователя.
            
        Returns:
            List[VolumeChangeListener]: Список слушателей, содержащих пользователя в подписчиках.
        """
        return [l for l in self._listeners.values() if user_id in l.subscribers]

    def unsubscribe_user_from_all(self, user_id: int) -> None:
        """Отписывает пользователя от всех активных слушателей.
        
        Удаляет указанного пользователя из списков подписчиков всех существующих
        слушателей. Не удаляет сами слушатели, даже если они остаются без подписчиков.
        
        Args:
            user_id (int): Идентификатор пользователя для глобальной отписки.
        """
        for listener in self._listeners.values():
            listener.remove_subscriber(user_id)

    async def _run_listener_periodically(
        self, listener: VolumeChangeListener, db_pool: asyncpg.Pool
    ) -> None:
        """Запускает бесконечный цикл проверки условий слушателя.
        
        Периодически вызывает метод проверки условий слушателя с интервалом,
        заданным в самом слушателе. Выполняется как фоновая асинхронная задача.
        
        Args:
            listener (VolumeChangeListener): Слушатель для периодической проверки.
            db_pool (asyncpg.Pool): Пул соединений с базой данных.
        """
        while True:
            await listener.check_and_notify(db_pool)
            await asyncio.sleep(listener.interval)


volume_change_listener_manager = VolumeChangeListenerManager()

async def get_volume_change_listener_manager() -> VolumeChangeListenerManager:
    """Возвращает экземпляр синглтона менеджера слушателей объёма.
    
    Ленивая фабрика для получения глобального экземпляра VolumeListenerManager.
    Обеспечивает единую точку доступа к менеджеру в рамках приложения.
    
    Returns:
        VolumeChangeListenerManager: Глобальный экземпляр менеджера слушателей.
    """
    return volume_change_listener_manager
