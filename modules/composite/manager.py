from typing import List, Dict

from .ast_transform import Expr
from .composite_listener import CompositeListener
from .utils import ast_to_string


class CompositeListenerManager:
    """
    Singleton‑менеджер CompositeListener‑ов.

    Attributes:
        _instance (CompositeListenerManager | None): Экземпляр синглтона.
        _listeners (Dict[str, CompositeListener]): Словарь слушателей по ID.
    """

    _instance: "CompositeListenerManager | None" = None

    def __init__(self) -> None:
        """
        Инициализация менеджера композитных слушателей.
        """
        self._listeners: Dict[str, CompositeListener] = {}

    @classmethod
    def instance(cls) -> "CompositeListenerManager":
        """
        Возвращает (и при необходимости создаёт) экземпляр менеджера.

        Returns:
            CompositeListenerManager: Экземпляр менеджера.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _generate_condition_id(self, expr: Expr) -> str:
        """
        Генерирует уникальный детерминированный ID для композитного условия.

        Хешируется строковое представление AST выражения.

        Args:
            expr (Expr): AST выражение условия алерта.

        Returns:
            str: Строковый идентификатор (числовой хеш).
        """
        expr_string = ast_to_string(expr)
        return str(hash(expr_string))

    async def add_listener(self, expr: Expr, user_id: int) -> CompositeListener:
        """
        Создаёт или подписывает на существующий композитный слушатель.

        Если слушатель с таким условием уже существует, пользователь подписывается
        на него. Иначе создаётся новый слушатель.

        Args:
            expr (Expr): Корневой AST.
            user_id (int): Владелец алерта.

        Returns:
            CompositeListener: Слушатель (новый или существующий).
        """
        condition_id = self._generate_condition_id(expr)
        
        if condition_id in self._listeners:
            existing_listener = self._listeners[condition_id]
            existing_listener.add_subscriber(user_id)
            print(f"[COMPOSITE] Подписка пользователя {user_id} на существующий слушатель {condition_id}")
            return existing_listener
        else:
            listener = CompositeListener(expr, user_id, condition_id)
            await listener.start()
            self._listeners[condition_id] = listener
            print(f"[COMPOSITE] Создан новый слушатель {condition_id} для пользователя {user_id}")
            return listener
        
    async def remove_listener(self, condition_id: str) -> bool:
        """
        Удаляет слушатель по ID.

        Args:
            condition_id (str): ID слушателя для удаления.

        Returns:
            bool: True если слушатель был удалён, False если не найден.
        """
        if condition_id not in self._listeners:
            print(f"[COMPOSITE] Слушатель {condition_id} не найден для удаления")
            return False
        
        listener = self._listeners[condition_id]
        try:
            await listener.stop()
        except Exception as exc:
            print(f"[COMPOSITE] Ошибка при остановке композитного слушателя: {exc}")
        
        del self._listeners[condition_id]
        print(f"[COMPOSITE] Слушатель {condition_id} удалён")
        return True

    async def unsubscribe_user(self, condition_id: str, user_id: int) -> bool:
        """
        Отписывает пользователя от слушателя.

        Если после отписки в слушателе не остаётся подписчиков,
        слушатель автоматически удаляется.

        Args:
            condition_id (str): ID слушателя.
            user_id (int): ID пользователя для отписки.

        Returns:
            bool: True если пользователь был отписан, False если слушатель не найден.
        """
        if condition_id not in self._listeners:
            print(f"[COMPOSITE] Слушатель {condition_id} не найден для отписки пользователя {user_id}")
            return False
        
        listener = self._listeners[condition_id]
        
        if user_id not in listener.subscribers:
            print(f"[COMPOSITE] Пользователь {user_id} не подписан на слушатель {condition_id}")
            return False
        
        listener.remove_subscriber(user_id)
        print(f"[COMPOSITE] Пользователь {user_id} отписан от слушателя {condition_id}")
        
        if not listener.subscribers:
            print(f"[COMPOSITE] Слушатель {condition_id} не имеет подписчиков, удаляем")
            await self.remove_listener(condition_id)
        
        return True

    async def remove_user_from_all_listeners(self, user_id: int) -> int:
        """
        Отписывает пользователя от всех слушателей.

        Args:
            user_id (int): ID пользователя для отписки.

        Returns:
            int: Количество слушателей, от которых пользователь был отписан.
        """
        removed_count = 0
        listeners_to_remove = []
        
        for condition_id, listener in self._listeners.items():
            if user_id in listener.subscribers:
                listener.remove_subscriber(user_id)
                removed_count += 1
                print(f"[COMPOSITE] Пользователь {user_id} отписан от слушателя {condition_id}")
                
                if not listener.subscribers:
                    listeners_to_remove.append(condition_id)
        
        for condition_id in listeners_to_remove:
            await self.remove_listener(condition_id)
        
        return removed_count

    async def tick(self) -> None:
        """
        Вызывается scheduler‑ом; проверяет только те listeners, у которых подошёл интервал.

        Returns:
            None
        """
        for listener_id, listener in self._listeners.items():
            print("[TICK]", listener_id)
            await listener.maybe_update()

    def get_listener_by_id(self, condition_id: str) -> CompositeListener | None:
        """
        Возвращает слушатель по ID условия.

        Args:
            condition_id (str): ID условия.

        Returns:
            CompositeListener | None: Слушатель или None если не найден.
        """
        return self._listeners.get(condition_id)

    def get_user_subscriptions(self, user_id: int) -> List[str]:
        """
        Возвращает список ID слушателей, на которые подписан пользователь.

        Args:
            user_id (int): ID пользователя.

        Returns:
            List[str]: Список ID слушателей.
        """
        subscriptions = []
        for condition_id, listener in self._listeners.items():
            if user_id in listener.subscribers:
                subscriptions.append(condition_id)
        return subscriptions
