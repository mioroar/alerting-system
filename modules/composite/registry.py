from typing import Awaitable, Callable, Dict

from .ast_transform import Condition
from ..listener import Listener
from ..price.listener.manager import get_price_listener_manager
from ..oi.listener.manager    import get_oi_listener_manager
from ..funding.listener.manager import get_funding_listener_manager
from ..volume.listener.manager import get_volume_amount_listener_manager
from ..volume_change.listener.manager import get_volume_change_listener_manager
from ..order.listener.manager import get_order_listener_manager

ListenerFactory = Callable[[Condition, int], Awaitable[Listener]]

_registry: Dict[str, ListenerFactory] = {}


def register(module: str, factory: ListenerFactory) -> None:
    """Регистрирует фабрику в глобальном реестре.

    Args:
        module: Ключ, который приходит из парсера (`condition.module`).
        factory: Короутина‑фабрика. На вход — AST‑Condition и user_id,
            на выход — condition_id созданного/найденного Listener'а.
    """
    _registry[module] = factory


async def create_listener(cond: Condition, uid: int) -> Listener:
    """Создаёт (или возвращает) Listener по AST‑условию.

    Args:
        cond: Лист AST (`module`, `op`, `params`).
        uid: Telegram‑ID автора алерта.

    Returns:
        str: condition_id зарегистрированного Listener'а.

    Raises:
        KeyError: Если модуль не зарегистрирован.
    """
    return await _registry[cond.module](cond, uid)


async def _price_factory(cond: Condition, _) -> Listener:
    """price >|< percent interval → PriceListener"""
    percent = float(cond.params[0])
    window  = int(cond.params[1])
    poll    = int(cond.params[2]) if len(cond.params) >= 3 else window
    manager = await get_price_listener_manager()
    listener = await manager.add_listener(
        {
            "direction": cond.op,
            "percent":  percent,
            "interval": poll,
            "window_sec": window,
        },
        user_id=None,
    )
    return listener


async def _oi_factory(cond: Condition, _) -> Listener:
    """oi >|< percent → OIListener (interval автоматически подставляется)"""
    manager = await get_oi_listener_manager()
    params = {
        "direction": cond.op,
        "percent":  cond.params[0],
        # interval подставится автоматически в OIListenerManager
    }
    listener = await manager.add_listener(params, user_id=None)
    return listener


async def _funding_factory(cond: Condition, _) -> Listener:
    """funding >|< percent time_threshold_sec → FundingListener"""
    manager = await get_funding_listener_manager()
    listener = await manager.add_listener(
        {
            "direction": cond.op,
            "percent":  cond.params[0],
            "time_threshold_sec": int(cond.params[1]),
        },
        user_id=None,
    )
    return listener


async def _volume_factory(cond: Condition, _) -> Listener:
    """volume >|< amount_usd interval_sec → VolumeAmountListener"""
    amount = float(cond.params[0])
    window = int(cond.params[1])
    poll = int(cond.params[2]) if len(cond.params) == 3 else window
    manager = await get_volume_amount_listener_manager()
    listener = await manager.add_listener(
        {
            "direction": cond.op,
            "percent": amount,
            "interval": poll,
            "window_sec": window,
        },
        user_id=None,
    )
    return listener


async def _volume_change_factory(cond: Condition, _) -> Listener:
    """volume_change >|< percent interval_sec → VolumeChangeListener"""
    percent = float(cond.params[0])
    window  = int(cond.params[1])
    poll    = int(cond.params[2]) if len(cond.params) >= 3 else window
    manager = await get_volume_change_listener_manager()
    listener = await manager.add_listener(
        {
            "direction": cond.op,
            "percent":  percent,
            "interval": poll,
            "window_sec": window,
        },
        user_id=None,
    )
    return listener

# async def _order_factory(cond: Condition, _) -> Listener:
#     """order >|< size_usd percent duration_sec → OrderListener"""
#     size_usd = float(cond.params[0])
#     max_percent = float(cond.params[1]) 
#     min_duration = int(cond.params[2])
    
#     manager = await get_order_listener_manager()
    
#     # Создаем параметры для OrderListener
#     params = {
#         "direction": cond.op,
#         "size_usd": size_usd,
#         "max_percent": max_percent,
#         "min_duration": min_duration,
#         "interval": 60,  # Период проверки order-слушателя
#     }
    
#     # Создаем слушатель через менеджер
#     listener = await manager.add_listener(params, user_id=None)
    
#     return listener


# регистрируем при импорте модуля
register("price", _price_factory)
register("oi",    _oi_factory)
register("funding", _funding_factory)
register("volume", _volume_factory)
register("volume_change", _volume_change_factory)
# register("order", _order_factory)