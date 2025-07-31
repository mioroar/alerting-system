from html import escape
from typing import List

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from .modules.price import price_router
from .modules.volume import volume_router
from .modules.volume_change import volume_change_router
from .modules.oi import oi_router
from .modules.funding import funding_router
from .modules.composite import alert_router

from modules.price.listener.manager import get_price_listener_manager
from modules.volume.listener.manager import get_volume_amount_listener_manager
from modules.volume_change.listener.manager import get_volume_change_listener_manager
from modules.oi.listener.manager import get_oi_listener_manager
from modules.funding.listener.manager import get_funding_listener_manager
from modules.composite.manager import CompositeListenerManager
from modules.composite.utils import ast_to_string

another_router: Router = Router()

another_router.include_router(price_router)
another_router.include_router(volume_router)
another_router.include_router(volume_change_router)
another_router.include_router(oi_router)
another_router.include_router(funding_router)
another_router.include_router(alert_router)

def _esc(val: object) -> str:
    """Надёжно экранирует любую переменную для HTML.

    Args:
        val: Произвольное значение.

    Returns:
        Экранированная строка, безопасная для вставки в HTML‑сообщение.
    """
    return escape(str(val), quote=False)


def _add_section(header: str, rows: List[str], dest: List[str]) -> None:
    """Добавляет секцию в результирующий список частей сообщения.

    Args:
        header: HTML‑заголовок секции (уже экранировать не нужно).
        rows:  Список подготовленных строк‑элементов секции.
        dest:  Список, в который будет добавлена секция.
    """
    if rows:
        dest.append(header)
        dest.extend(rows)


@another_router.message(Command("get_all_listeners"))
async def get_all_listeners_handler(message: Message) -> None:
    """Выводит все активные подписки пользователя.

    Args:
        message: Входящее сообщение Telegram с командой «/get_all_listeners».
    """
    user_id: int = message.from_user.id

    price_manager = await get_price_listener_manager()
    volume_amount_manager = await get_volume_amount_listener_manager()
    volume_change_manager = await get_volume_change_listener_manager()
    oi_manager = await get_oi_listener_manager()
    funding_manager = await get_funding_listener_manager()
    composite_manager = CompositeListenerManager.instance()

    price_listeners = price_manager.get_all_user_listeners(user_id)
    volume_amount_listeners = volume_amount_manager.get_all_user_listeners(user_id)
    volume_change_listeners = volume_change_manager.get_all_user_listeners(user_id)
    oi_listeners = oi_manager.get_all_user_listeners(user_id)
    funding_listeners = funding_manager.get_all_user_listeners(user_id)
    composite_subscriptions = composite_manager.get_user_subscriptions(user_id)

    parts: List[str] = []

    _add_section(
        "<b>💰 Подписки на изменения цены:</b>",
        [
            (
                f"• Изменение цены {_esc(l.direction)} {_esc(l.percent)}% "
                f"за {_esc(l.interval)} с.\n"
                f"  ID: <code>{_esc(l.get_condition_id())}</code>"
            )
            for l in price_listeners
        ],
        parts,
    )

    _add_section(
        "<b>📊 Подписки на абсолютный объём:</b>",
        [
            (
                f"• Объём {'превысил' if l.direction == '>' else 'опустился ниже'} "
                f"{_esc(l.amount):,.0f} USD за {_esc(l.interval)} с.\n"
                f"  ID: <code>{_esc(l.get_condition_id())}</code>"
            )
            for l in volume_amount_listeners
        ],
        parts,
    )

    _add_section(
        "<b>📈 Подписки на изменения OI:</b>",
        [
            (
                f"• Изменение OI {_esc(l.direction)} {_esc(l.percent)}% "
                f"за {_esc(l.interval)} с.\n"
                f"  ID: <code>{_esc(l.get_condition_id())}</code>"
            )
            for l in oi_listeners
        ],
        parts,
    )

    _add_section(
        "<b>📈 Подписки на изменения объёма:</b>",
        [
            (
                f"• Изменение объёма {_esc(l.direction)} {_esc(l.percent)}% "
                f"за {_esc(l.interval)} с.\n"
                f"  ID: <code>{_esc(l.get_condition_id())}</code>"
            )
            for l in volume_change_listeners
        ],
        parts,
    )

    _add_section(
        "<b>📅 Подписки на funding:</b>",
        [
            (
                f"• funding {_esc(l.direction)}{_esc(l.percent)}% ≤ "
                f"{_esc(l.time_threshold_sec)} с.\n"
                f"  ID: <code>{_esc(l.get_condition_id())}</code>"
            )
            for l in funding_listeners
        ],
        parts,
    )

    composite_alerts = []
    for condition_id in composite_subscriptions:
        listener = composite_manager.get_listener_by_id(condition_id)
        if listener:
            expr_str = ast_to_string(listener._root)
            cooldown_info = f" (cooldown: {listener._cooldown}s)" if listener._cooldown > 0 else ""
            composite_alerts.append(
                f"• <code>{_esc(expr_str)}</code>{_esc(cooldown_info)}\n"
                f"  ID: <code>{_esc(condition_id)}</code>"
            )
    
    _add_section(
        "<b>🔗 Композитные алерты:</b>",
        composite_alerts,
        parts,
    )

    if not parts:
        await message.answer("У вас нет активных подписок.")
        return

    await message.answer("\n\n".join(parts), parse_mode=ParseMode.HTML)
