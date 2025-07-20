from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from modules.volume_change.listener.manager import get_volume_change_listener_manager

volume_change_router = Router()


@volume_change_router.message(Command("volume"))
async def volume_handler(message: Message) -> None:
    """Создает новый VolumeListener и/или подписывает пользователя на него.

    Команда принимает три аргумента:
    - percent: Процент изменения объёма.
    - interval: Интервал в секундах.
    - direction: Направление изменения ('>' или '<').

    Пример: /volume 50 60 >

    Если VolumeListener с такими параметрами уже существует, пользователь просто
    добавляется в список подписчиков.

    Args:
        message: Сообщение с командой.
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

        volume_listener_manager = await get_volume_change_listener_manager()
        await volume_listener_manager.add_listener(
            params=params,
            user_id=user_id
        )

        await message.answer(
            f"Вы подписаны на условие: изменение объёма {direction} {percent}% за {interval} сек."
        )
    except Exception as e:
        await message.answer(f"Ошибка: {e}\nПример: /volume 50 60 >")


@volume_change_router.message(Command("get_all_volume_listeners"))
async def get_all_volume_listeners_handler(message: Message) -> None:
    """Сообщает пользователю список всех его активных подписок на объём.

    Формат ответа — одно или несколько сообщений вида:
        Условие: изменение объёма > 50.0% за 60 сек.
        ID: 123456789

    Если подписок нет, бот возвращает лаконичное уведомление.

    Args:
        message: Сообщение Telegram, содержащее команду.
    """
    user_id = message.from_user.id
    volume_listener_manager = await get_volume_change_listener_manager()    
    listeners = volume_listener_manager.get_all_user_listeners(user_id)
    if listeners:
        await message.answer("Ваши подписки на изменения объёма:")
        for listener in listeners:
            await message.answer(
                f"Условие: изменение объёма > {listener.percent}% за {listener.interval} сек.\n"
                f"ID: {listener.get_condition_id()}"
            )
    else:
        await message.answer("У вас нет подписок на изменения объёма.")


@volume_change_router.message(Command("unsubscribe_from_volume_listener"))
async def unsubscribe_from_volume_listener_handler(message: Message) -> None:
    """Отписывает пользователя от конкретного условия объёма по его идентификатору.

    Ожидается ровно один аргумент после команды — condition_id.

    Пример:
        /unsubscribe_from_volume_listener 1234567890

    Args:
        message: Сообщение Telegram с текстом команды.
    """
    try:
        _, condition_id = message.text.split()
        volume_listener_manager = await get_volume_change_listener_manager()
        await volume_listener_manager.remove_listener(condition_id)
        await message.answer(f"Вы отписаны от условия объёма: {condition_id}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}\nПример: /unsubscribe_from_volume_listener 1234567890")


@volume_change_router.message(Command("unsubscribe_all_volume"))
async def unsubscribe_all_volume_handler(message: Message) -> None:
    """Отписывает пользователя от всех VolumeListener.

    Args:
        message: Сообщение Telegram с текстом команды.
    """
    volume_listener_manager = await get_volume_change_listener_manager()
    volume_listener_manager.unsubscribe_user_from_all_listeners(message.from_user.id)
    await message.answer("Вы отписаны от всех подписок на изменения объёма.") 