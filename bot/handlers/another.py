from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode
from .modules.price import price_router
from .modules.volume import volume_router
from .modules.volume_change import volume_change_router
from modules.price.listener.manager import get_price_listener_manager
from modules.volume.listener.manager import get_volume_amount_listener_manager
from modules.volume_change.listener.manager import get_volume_change_listener_manager

another_router = Router()

another_router.include_router(price_router)
another_router.include_router(volume_router) 
another_router.include_router(volume_change_router)


@another_router.message(Command("get_all_listeners"))
async def get_all_listeners_handler(message: Message) -> None:
    """Отображает все активные листенеры пользователя всех типов.
    
    Показывает подписки на:
    - Изменения цены
    - Абсолютный объём
    - Изменения объёма
    
    Args:
        message: Сообщение Telegram с командой.
    """
    user_id = message.from_user.id
    
    # Получаем все листенеры пользователя
    price_manager = await get_price_listener_manager()
    volume_amount_manager = await get_volume_amount_listener_manager()
    volume_change_manager = await get_volume_change_listener_manager()
    
    price_listeners = price_manager.get_all_user_listeners(user_id)
    volume_amount_listeners = volume_amount_manager.get_all_user_listeners(user_id)
    volume_change_listeners = volume_change_manager.get_all_user_listeners(user_id)
    
    # Формируем ответ
    response_parts = []
    
    if price_listeners:
        response_parts.append("<b>💰 Подписки на изменения цены:</b>")
        for listener in price_listeners:
            response_parts.append(
                f"• Изменение цены {listener.direction} {listener.percent}% за {listener.interval} сек.\n"
                f"  ID: <code>{listener.get_condition_id()}</code>"
            )
    
    if volume_amount_listeners:
        response_parts.append("<b>📊 Подписки на абсолютный объём:</b>")
        for listener in volume_amount_listeners:
            direction_text = "превысил" if listener.direction == ">" else "опустился ниже"
            response_parts.append(
                f"• Объём {direction_text} {listener.amount:,.0f} USD за {listener.interval} сек.\n"
                f"  ID: <code>{listener.get_condition_id()}</code>"
            )
    
    if volume_change_listeners:
        response_parts.append("<b>📈 Подписки на изменения объёма:</b>")
        for listener in volume_change_listeners:
            response_parts.append(
                f"• Изменение объёма {listener.direction} {listener.percent}% за {listener.interval} сек.\n"
                f"  ID: <code>{listener.get_condition_id()}</code>"
            )
    
    if not response_parts:
        await message.answer("У вас нет активных подписок.")
        return
    
    # Отправляем результат
    response = "\n\n".join(response_parts)
    await message.answer(response, parse_mode=ParseMode.HTML)

