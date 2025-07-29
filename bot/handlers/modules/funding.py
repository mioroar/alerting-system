from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from modules.funding.listener.manager import get_funding_listener_manager

funding_router = Router()


@funding_router.message(Command("funding"))
async def funding_handler(message: Message) -> None:
    """Создаёт FundingListener и подписывает пользователя.

    Формат команды: /funding <direction> <percent> <seconds_to_funding>

    Args:
        message: Объект сообщения от пользователя.

    Returns:
        None

    Raises:
        None

    Examples:
        /funding > 2 600   → алерт, если |ставка| ≥ 2 %, а до расчёта ≤ 600 с.
    """
    parts = message.text.split()
    if len(parts) != 4:
        await message.answer("Формат: /funding > 2 600")
        return

    _, direction, pct_str, sec_str = parts
    if direction not in (">", "<"):
        await message.answer("Направление должно быть '>' или '<'.")
        return

    try:
        percent = float(pct_str)
        seconds = int(sec_str)
    except ValueError:
        await message.answer("Процент и секунды должны быть числами.")
        return

    params = {
        "direction": direction,
        "percent": percent,
        "time_threshold_sec": seconds,
    }

    manager = await get_funding_listener_manager()
    await manager.add_listener(params=params, user_id=message.from_user.id)

    await message.answer(
        f"Подписка создана: funding {direction}{percent}% "
        f"и до расчёта ≤ {seconds} с."
    )


@funding_router.message(Command("get_all_funding_listeners"))
async def get_all_funding_listeners_handler(message: Message) -> None:
    """Показывает все активные подписки пользователя на funding-ставку.

    Args:
        message: Объект сообщения от пользователя.

    Returns:
        None

    Raises:
        None
    """
    user_id = message.from_user.id
    manager = await get_funding_listener_manager()
    listeners = manager.get_all_user_listeners(user_id)

    if not listeners:
        await message.answer("У вас нет подписок на funding.")
        return

    await message.answer("Ваши подписки на funding:")
    for lsn in listeners:
        await message.answer(
            f"• funding {lsn.direction}{lsn.percent}% "
            f"до расчёта ≤ {lsn.time_threshold_sec} с.\n"
            f"  ID: <code>{lsn.get_condition_id()}</code>",
            parse_mode="HTML",
        )


@funding_router.message(Command("unsubscribe_from_funding_listener"))
async def unsubscribe_from_funding_listener_handler(message: Message) -> None:
    """Отписывает от конкретного funding-условия по ID.

    Args:
        message: Объект сообщения от пользователя.

    Returns:
        None

    Raises:
        None

    Examples:
        /unsubscribe_from_funding_listener 1234567890
    """
    try:
        _, condition_id = message.text.split()
    except ValueError:
        await message.answer("Формат: /unsubscribe_from_funding_listener <ID>")
        return

    manager = await get_funding_listener_manager()
    await manager.remove_listener(condition_id)
    await message.answer(f"Отписка выполнена: {condition_id}")


@funding_router.message(Command("unsubscribe_all_funding"))
async def unsubscribe_all_funding_handler(message: Message) -> None:
    """Снимает все подписки пользователя на funding-ставку.

    Args:
        message: Объект сообщения от пользователя.

    Returns:
        None

    Raises:
        None
    """
    manager = await get_funding_listener_manager()
    manager.unsubscribe_user_from_all(message.from_user.id)
    await message.answer("Вы отписаны от всех условий funding.")
