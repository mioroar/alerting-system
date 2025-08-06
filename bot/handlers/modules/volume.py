from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from modules.volume.listener.manager import get_volume_amount_listener_manager

volume_router = Router()


@volume_router.message(Command("volume_amount"))
async def volume_amount_handler(message: Message) -> None:
    """Создает новый VolumeAmountListener и/или подписывает пользователя на него.

    Команда принимает три аргумента:
    - amount: Абсолютное значение объёма в USD.
    - interval: Интервал в секундах.
    - direction: Направление сравнения ('>' или '<').

    Пример: /volume_amount > 10000000 300

    Если VolumeAmountListener с такими параметрами уже существует, пользователь просто
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

        volume_amount_manager = await get_volume_amount_listener_manager()
        await volume_amount_manager.add_listener(
            params=params,
            user_id=user_id
        )

        direction_text = "превысил" if direction == ">" else "опустился ниже"
        await message.answer(
            f"Вы подписаны на условие: объём {direction_text} {percent:,.0f} USD за {interval} сек."
        )
    except Exception as e:
        from config import logger
        logger.exception(f"Volume amount handler error: {e}")
        await message.answer(f"Ошибка: {e}\nПример: /volume_amount >10000000 300")


@volume_router.message(Command("get_all_volume_amount_listeners"))
async def get_all_volume_amount_listeners_handler(message: Message) -> None:
    """Сообщает пользователю список всех его активных подписок на абсолютный объём.

    Формат ответа — одно или несколько сообщений вида:
        Условие: объём превысил 10,000,000 USD за 300 сек.
        ID: 123456789

    Если подписок нет, бот возвращает лаконичное уведомление.

    Args:
        message: Сообщение Telegram, содержащее команду.
    """
    user_id = message.from_user.id
    volume_amount_manager = await get_volume_amount_listener_manager()
    listeners = volume_amount_manager.get_all_user_listeners(user_id)
    if listeners:
        await message.answer("Ваши подписки на абсолютный объём:")
        for listener in listeners:
            direction_text = "превысил" if listener.direction == ">" else "опустился ниже"
            await message.answer(
                f"Условие: объём {direction_text} {listener.percent:,.0f} USD за {listener.interval} сек.\n"
                f"ID: {listener.get_condition_id()}"
            )
    else:
        await message.answer("У вас нет подписок на абсолютный объём.")


@volume_router.message(Command("unsubscribe_from_volume_amount_listener"))
async def unsubscribe_from_volume_amount_listener_handler(message: Message) -> None:
    """Отписывает пользователя от конкретного условия абсолютного объёма по ID.

    Ожидается ровно один аргумент после команды — condition_id.

    Пример:
        /unsubscribe_from_volume_amount_listener 1234567890

    Args:
        message: Сообщение Telegram с текстом команды.
    """
    try:
        _, condition_id = message.text.split()
        volume_amount_manager = await get_volume_amount_listener_manager()
        await volume_amount_manager.remove_listener(condition_id)
        await message.answer(f"Вы отписаны от условия абсолютного объёма: {condition_id}")
    except Exception as e:
        from config import logger
        logger.exception(f"Volume amount unsubscribe error: {e}")
        await message.answer(f"Ошибка: {e}\nПример: /unsubscribe_from_volume_amount_listener 1234567890")


@volume_router.message(Command("unsubscribe_all_volume_amount"))
async def unsubscribe_all_volume_amount_handler(message: Message) -> None:
    """Отписывает пользователя от всех VolumeAmountListener.

    Args:
        message: Сообщение Telegram с текстом команды.
    """
    volume_amount_manager = await get_volume_amount_listener_manager()
    volume_amount_manager.unsubscribe_user_from_all(message.from_user.id)
    await message.answer("Вы отписаны от всех подписок на абсолютный объём.") 