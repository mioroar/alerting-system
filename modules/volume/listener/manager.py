from modules.manager import BaseListenerManager
from modules.volume.listener.logic import VolumeAmountListener


class VolumeAmountListenerManager(BaseListenerManager[VolumeAmountListener]):
    """Менеджер для VolumeAmountListener."""
    def __init__(self) -> None:
        super().__init__(VolumeAmountListener)

volume_amount_listener_manager = VolumeAmountListenerManager()

async def get_volume_amount_listener_manager() -> VolumeAmountListenerManager:
    """Возвращает экземпляр синглтона менеджера слушателей объёма.

    Returns:
        Глобальный экземпляр VolumeAmountListenerManager.
    """
    return volume_amount_listener_manager
