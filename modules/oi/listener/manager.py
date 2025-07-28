from modules.manager import BaseListenerManager
from modules.oi.listener.logic import OIListener
from modules.oi.config import OI_CHECK_INTERVAL_SEC

class OIListenerManager(BaseListenerManager[OIListener]):
    """Хеш‑таблица condition_id → OIListener."""

    def __init__(self) -> None:
        super().__init__(OIListener)

    async def add_listener(self, params: dict, user_id: int) -> OIListener:
        """
        Создаёт или возвращает OI‑слушатель.

        • Если «interval» отсутствует, подставляется ``OI_CHECK_INTERVAL_SEC``
            (24 ч), чтобы удовлетворить базовый менеджер.
        """
        params = params.copy()
        params.setdefault("interval", OI_CHECK_INTERVAL_SEC)
        return await super().add_listener(params, user_id)


_oi_listener_manager: OIListenerManager | None = None


async def get_oi_listener_manager() -> OIListenerManager:
    """Ленивая синглтон‑фабрика."""
    global _oi_listener_manager
    if _oi_listener_manager is None:
        _oi_listener_manager = OIListenerManager()
    return _oi_listener_manager
