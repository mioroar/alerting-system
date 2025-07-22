from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from modules.price.listener.manager import get_price_listener_manager

price_router = Router()


@price_router.message(Command("price"))
async def price_handler(message: Message) -> None:
    """Создает новый PriceListener и/или подписывает пользователя на него.

    Команда принимает два аргумента:
    - percent: Процент изменения цены.
    - interval: Интервал в секундах.

    Пример: /price > 5 60

    Если PriceListener с такими параметрами уже существует, пользователь просто
    добавляется в список подписчиков.

    Args:
        message: Сообщение с командой.
    """
    try:
        _, direction, percent, interval = message.text.split()
        percent = float(percent)
        interval = int(interval)
        user_id = message.from_user.id

        params = {
            "direction": direction,
            "percent": percent,
            "interval": interval,
        }

        price_listener_manager = await get_price_listener_manager()
        await price_listener_manager.add_listener(
            params=params,
            user_id=user_id
        )

        await message.answer(
            f"Вы подписаны на условие: изменение цены {direction} {percent}% за {interval} сек."
        )
    except Exception as e:
        await message.answer(f"Ошибка: {e}\nПример: /price > 5 60")


@price_router.message(Command("get_all_price_listeners"))
async def get_all_price_listeners_handler(message: Message) -> None:
    """Сообщает пользователю список всех его активных подписок на цену.

    Формат ответа — одно или несколько сообщений вида:
        Условие: изменение цены > 5.0% за 60 сек.
        ID: 123456789

    Если подписок нет, бот возвращает лаконичное уведомление.

    Args:
        message: Сообщение Telegram, содержащее команду.
    """
    user_id = message.from_user.id
    price_listener_manager = await get_price_listener_manager()
    listeners = price_listener_manager.get_all_user_listeners(user_id)
    if listeners:
        await message.answer("Ваши подписки на изменения цены:")
        for listener in listeners:
            await message.answer(
                f"Условие: изменение цены {listener.direction} {listener.percent}% за {listener.interval} сек.\n"
                f"ID: {listener.get_condition_id()}"
            )
    else:
        await message.answer("У вас нет подписок на изменения цены.")


@price_router.message(Command("unsubscribe_from_price_listener"))
async def unsubscribe_from_price_listener_handler(message: Message) -> None:
    """Отписывает пользователя от конкретного условия цены по его идентификатору.

    Ожидается ровно один аргумент после команды — condition_id.

    Пример:
        /unsubscribe_from_price_listener 1234567890

    Args:
        message: Сообщение Telegram с текстом команды.
    """
    try:
        _, condition_id = message.text.split()
        price_listener_manager = await get_price_listener_manager()
        await price_listener_manager.remove_listener(condition_id)
        await message.answer(f"Вы отписаны от условия цены: {condition_id}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}\nПример: /unsubscribe_from_price_listener 1234567890")


@price_router.message(Command("unsubscribe_all_price"))
async def unsubscribe_all_price_handler(message: Message) -> None:
    """Отписывает пользователя от всех PriceListener.

    Args:
        message: Сообщение Telegram с текстом команды.
    """
    price_listener_manager = await get_price_listener_manager()
    price_listener_manager.unsubscribe_user_from_all_listeners(message.from_user.id)
    await message.answer("Вы отписаны от всех подписок на изменения цены.") 