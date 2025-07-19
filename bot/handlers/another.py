from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from modules.price.listener.manager import get_listener_manager
from modules.volume_change.listener.manager import get_volume_listener_manager

another_router = Router()

@another_router.message(Command("price"))
async def price_handler(message: Message) -> None:
    """Создает новый PriceListener и/или подписывает пользователя на него.

    Команда принимает два аргумента:
    - percent: Процент изменения цены.
    - interval: Интервал в секундах.

    Пример: /price 5 60

    Если PriceListener с такими параметрами уже существует, пользователь просто
    добавляется в список подписчиков.

    Args:
        message (Message): Сообщение с командой.
    """
    try:
        _, percent, interval = message.text.split()
        percent = float(percent)
        interval = int(interval)
        user_id = message.from_user.id

        params = {
            "percent": percent,
            "interval": interval
        }

        listener_manager = await get_listener_manager()
        await listener_manager.add_listener(
            params=params,
            user_id=user_id
        )

        await message.answer(
            f"Вы подписаны на условие: изменение цены > {percent}% за {interval} сек."
        )
    except Exception as e:
        await message.answer(f"Ошибка: {e}\nПример: /price 5 60")

@another_router.message(Command("volume"))
async def volume_handler(message: Message) -> None:
    """Создает новый VolumeListener и/или подписывает пользователя на него.

    Команда принимает два аргумента:
    - percent: Процент изменения объёма.
    - interval: Интервал в секундах.

    Пример: /volume 50 60 >

    Если VolumeListener с такими параметрами уже существует, пользователь просто
    добавляется в список подписчиков.

    Args:
        message (Message): Сообщение с командой.
    """
    try:
        _, percent, interval, direction = message.text.split()
        percent = float(percent)
        interval = int(interval)
        user_id = message.from_user.id

        params = {
            "percent": percent,
            "interval": interval,
            "direction": direction
        }

        volume_listener_manager = await get_volume_listener_manager()
        await volume_listener_manager.add_listener(
            params=params,
            user_id=user_id
        )

        await message.answer(
            f"Вы подписаны на условие: изменение объёма {direction} {percent}% за {interval} сек."
        )
    except Exception as e:
        await message.answer(f"Ошибка: {e}\nПример: /volume 50 60")

@another_router.message(Command("get_all_price_listeners"))
async def get_all_price_listeners_handler(message: Message) -> None:
    """Сообщает пользователю список всех его активных подписок на цену.

    Формат ответа — одно или несколько сообщений вида:
        Условие: изменение цены > 5.0% за 60 сек.
        ID: 123456789

    Если подписок нет, бот возвращает лаконичное уведомление.

    Args:
        message (Message): Сообщение Telegram, содержащее команду.
    """
    user_id = message.from_user.id
    listener_manager = await get_listener_manager()
    listeners = listener_manager.get_all_user_listeners(user_id)
    if listeners:
        await message.answer("Ваши подписки на изменения цены:")
        for listener in listeners:
            await message.answer(f"Условие: изменение цены > {listener.percent}% за {listener.interval} сек.\nID: {listener.get_condition_id()}")
    else:
        await message.answer("У вас нет подписок на изменения цены.")

@another_router.message(Command("get_all_volume_listeners"))
async def get_all_volume_listeners_handler(message: Message) -> None:
    """Сообщает пользователю список всех его активных подписок на объём.

    Формат ответа — одно или несколько сообщений вида:
        Условие: изменение объёма > 50.0% за 60 сек.
        ID: 123456789

    Если подписок нет, бот возвращает лаконичное уведомление.

    Args:
        message (Message): Сообщение Telegram, содержащее команду.
    """
    user_id = message.from_user.id
    volume_listener_manager = await get_volume_listener_manager()
    listeners = volume_listener_manager.get_all_user_listeners(user_id)
    if listeners:
        await message.answer("Ваши подписки на изменения объёма:")
        for listener in listeners:
            await message.answer(f"Условие: изменение объёма > {listener.percent}% за {listener.interval} сек.\nID: {listener.get_condition_id()}")
    else:
        await message.answer("У вас нет подписок на изменения объёма.")

@another_router.message(Command("unsubscribe_from_price_listener"))
async def unsubscribe_from_price_listener_handler(message: Message) -> None:
    """Отписывает пользователя от конкретного условия цены по его идентификатору.

    Ожидается ровно один аргумент после команды — condition_id.

    Пример:
        /unsubscribe_from_price_listener 1234567890

    Args:
        message (Message): Сообщение Telegram с текстом команды.
    """
    try:
        _, condition_id = message.text.split()
        listener_manager = await get_listener_manager()
        await listener_manager.remove_listener(condition_id)
        await message.answer(f"Вы отписаны от условия цены: {condition_id}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}\nПример: /unsubscribe_from_price_listener 1234567890")

@another_router.message(Command("unsubscribe_from_volume_listener"))
async def unsubscribe_from_volume_listener_handler(message: Message) -> None:
    """Отписывает пользователя от конкретного условия объёма по его идентификатору.

    Ожидается ровно один аргумент после команды — condition_id.

    Пример:
        /unsubscribe_from_volume_listener 1234567890

    Args:
        message (Message): Сообщение Telegram с текстом команды.
    """
    try:
        _, condition_id = message.text.split()
        volume_listener_manager = await get_volume_listener_manager()
        await volume_listener_manager.remove_listener(condition_id)
        await message.answer(f"Вы отписаны от условия объёма: {condition_id}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}\nПример: /unsubscribe_from_volume_listener 1234567890")

@another_router.message(Command("unsubscribe_all_price"))
async def unsubscribe_all_price_handler(message: Message) -> None:
    """Отписывает пользователя от всех PriceListener.

    Args:
        message (Message): Сообщение Telegram с текстом команды.
    """
    listener_manager = await get_listener_manager()
    listener_manager.unsubscribe_user_from_all_listeners(message.from_user.id)
    await message.answer("Вы отписаны от всех подписок на изменения цены.")

@another_router.message(Command("unsubscribe_all_volume"))
async def unsubscribe_all_volume_handler(message: Message) -> None:
    """Отписывает пользователя от всех VolumeListener.

    Args:
        message (Message): Сообщение Telegram с текстом команды.
    """
    volume_listener_manager = await get_volume_listener_manager()
    volume_listener_manager.unsubscribe_user_from_all_listeners(message.from_user.id)
    await message.answer("Вы отписаны от всех подписок на изменения объёма.")