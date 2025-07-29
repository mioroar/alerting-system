from typing import List

from .ast_transform import Expr
from .composite_listener import CompositeListener


class CompositeListenerManager:
    """Singleton‑менеджер CompositeListener‑ов."""

    _instance: "CompositeListenerManager | None" = None

    def __init__(self) -> None:
        self._listeners: List[CompositeListener] = []

    @classmethod
    def instance(cls) -> "CompositeListenerManager":
        """Возвращает (и при необходимости создаёт) экземпляр менеджера."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def add_listener(self, expr: Expr, user_id: int) -> CompositeListener:
        """Создаёт и регистрирует композитный слушатель.

        Args:
            expr: Корневой AST.
            user_id: Владелец алерта.

        Returns:
            CompositeListener: Запущенный слушатель.
        """
        listener = CompositeListener(expr, user_id)
        await listener.start()
        self._listeners.append(listener)
        return listener

    async def tick(self) -> None:
        """Вызывается scheduler‑ом; проверяет только те listeners, у которых подошёл интервал."""
        for lst in self._listeners:
            print("[TICK]", lst.id)
            await lst.maybe_update()
