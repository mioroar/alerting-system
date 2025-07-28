from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from modules.oi.listener.manager import get_oi_listener_manager

oi_router = Router()


@oi_router.message(Command("oi"))
async def oi_handler(message: Message) -> None:
    """
    Создаёт новый OIListener и/или подписывает пользователя.

    Формат команды:
        /oi <direction> <percent>

    • direction — «>» или «<».
    • percent   — порог отклонения от медианы в процентах.

    Пример:
        /oi > 200
    """
    try:
        _, direction, percent = message.text.split()
        percent = float(percent)
        user_id = message.from_user.id

        params = {"direction": direction, "percent": percent}

        oi_manager = await get_oi_listener_manager()
        await oi_manager.add_listener(params=params, user_id=user_id)

        direction_txt = "выше" if direction == ">" else "ниже"
        await message.answer(
            f"Вы подписаны: OI {direction_txt} медианы на {percent:.1f}%."
        )
    except Exception as exc:
        await message.answer(f"Ошибка: {exc}\nПример: /oi > 200")


@oi_router.message(Command("get_all_oi_listeners"))
async def get_all_oi_listeners_handler(message: Message) -> None:
    """Показывает все активные подписки пользователя на OI."""
    user_id = message.from_user.id
    oi_manager = await get_oi_listener_manager()
    listeners = oi_manager.get_all_user_listeners(user_id)

    if not listeners:
        await message.answer("У вас нет подписок на OI.")
        return

    await message.answer("Ваши подписки на отклонение OI от медианы:")
    for listener in listeners:
        direction_txt = "выше" if listener.direction == ">" else "ниже"
        await message.answer(
            f"• OI {direction_txt} медианы на {listener.percent:.1f}%\n"
            f"  ID: {listener.get_condition_id()}"
        )


@oi_router.message(Command("unsubscribe_from_oi_listener"))
async def unsubscribe_from_oi_listener_handler(message: Message) -> None:
    """
    Отписывает пользователя от конкретного OI‑условия по ID.

    Формат:
        /unsubscribe_from_oi_listener <condition_id>
    """
    try:
        _, condition_id = message.text.split()
        oi_manager = await get_oi_listener_manager()
        await oi_manager.remove_listener(condition_id)
        await message.answer(f"Отписка выполнена: {condition_id}")
    except Exception as exc:
        await message.answer(
            f"Ошибка: {exc}\nПример: /unsubscribe_from_oi_listener 1234567890"
        )


@oi_router.message(Command("unsubscribe_all_oi"))
async def unsubscribe_all_oi_handler(message: Message) -> None:
    """Мгновенно снимает все подписки пользователя на OI."""
    oi_manager = await get_oi_listener_manager()
    oi_manager.unsubscribe_user_from_all_listeners(message.from_user.id)
    await message.answer("Вы отписаны от всех условий OI.")
