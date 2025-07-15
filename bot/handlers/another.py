from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from modules.price.listener.manager import get_listener_manager

another_router = Router()

@another_router.message(Command("listen"))
async def listen_handler(message: Message):
    """
    Команда для создания листенера.
    Пример: /listen 5 60
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
            f"Вы подписаны на условие: изменение > {percent}% за {interval} сек."
        )
    except Exception as e:
        await message.answer(f"Ошибка: {e}\nПример: /listen 5 60")

@another_router.message(Command("get_all_listeners"))
async def get_all_listeners_handler(message: Message):
    user_id = message.from_user.id
    listener_manager = await get_listener_manager()
    listeners = listener_manager.get_all_user_listeners(user_id)
    if listeners:
        await message.answer("Ваши подписки:")
        for listener in listeners:
            await message.answer(f"Условие: изменение > {listener.percent}% за {listener.interval} сек.\nID: {listener.get_condition_id()}")
    else:
        await message.answer("У вас нет подписок.")

@another_router.message(Command("unsubscribe_from_listener"))
async def unsubscribe_from_listener_handler(message: Message):
    try:
        _, condition_id = message.text.split()
        listener_manager = await get_listener_manager()
        await listener_manager.remove_listener(condition_id)
        await message.answer(f"Вы отписаны от условия: {condition_id}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}\nПример: /unsubscribe_from_listener 1234567890")