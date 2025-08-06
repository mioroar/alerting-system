import asyncio
import datetime as dt
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from modules.composite.utils import parse_expression, ast_to_string
from modules.composite.manager import CompositeListenerManager

alert_router: Router = Router()

async def composite_loop(base_step: int = 5) -> None:
    mgr = CompositeListenerManager.instance()
    while True:
        try:
            await mgr.tick()
        except Exception as exc:
            from config import logger
            logger.exception(f"Composite tick failed: {exc}")
        await asyncio.sleep(base_step)

@alert_router.message(Command("alert"))
async def alert_handler(message: Message) -> None:
    """Создаёт/подписывает композитный алерт из текста команды Telegram.

    Ожидаемый формат:
        /alert <expr>

    Пример:
        /alert price > 5 300 & oi < 100 @10

    Args:
        message: Объект сообщения Telegram.
    """
    user_id: int = message.from_user.id
    # Обрезаем лишь префикс "/alert ", остальное считаем выражением.
    expr_text: str = message.text.removeprefix("/alert").strip()

    if not expr_text:
        await message.answer("После /alert должно идти выражение условий.")
        return

    try:
        ast = parse_expression(expr_text)
    except Exception as exc:
        from config import logger
        logger.exception(f"Composite expression parse error: {exc}")
        await message.answer(f"Синтаксическая ошибка: <code>{exc}</code>", parse_mode="HTML")
        return

    manager = CompositeListenerManager.instance()
    await manager.add_listener(ast, user_id)
    print("[MAN]", len(manager._listeners), "comp‑listeners total")

    await message.answer(
        "✅ Композитный алерт зарегистрирован и начнёт проверяться в течение нескольких секунд."
    )

@alert_router.message(Command("unsubscribe"))
async def unsubscribe_handler(message: Message) -> None:
    """Отписывает от конкретного композитного алерта по ID.

    Ожидаемый формат:
        /unsubscribe <ID>

    Пример:
        /unsubscribe 1234567890

    Args:
        message: Объект сообщения Telegram.
    """
    user_id: int = message.from_user.id
    id_text: str = message.text.removeprefix("/unsubscribe").strip()

    if not id_text:
        await message.answer("После /unsubscribe должно идти ID алерта.")
        return

    try:
        condition_id: str = id_text
    except ValueError:
        await message.answer("ID алерта должен быть числом.")
        return

    manager = CompositeListenerManager.instance()
    success = await manager.unsubscribe_user(condition_id, user_id)
    
    if success:
        await message.answer(
            f"✅ Вы отписались от алерта с ID: <code>{condition_id}</code>",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "❌ Алерт не найден или вы не подписаны на него."
        )

@alert_router.message(Command("unsubscribe_all"))
async def unsubscribe_all_handler(message: Message) -> None:
    """Отписывает от всех композитных алертов.

    Ожидаемый формат:
        /unsubscribe_all

    Args:
        message: Объект сообщения Telegram.
    """
    user_id: int = message.from_user.id
    manager = CompositeListenerManager.instance()
    
    removed_count = await manager.remove_user_from_all_listeners(user_id)
    
    if removed_count > 0:
        await message.answer(
            f"✅ Вы отписались от {removed_count} алертов."
        )
    else:
        await message.answer(
            "ℹ️ У вас нет активных подписок на композитные алерты."
        )

@alert_router.message(Command("my_alerts"))
async def my_alerts_handler(message: Message) -> None:
    """Показывает все алерты, на которые подписан пользователь.

    Ожидаемый формат:
        /my_alerts

    Args:
        message: Объект сообщения Telegram.
    """
    user_id: int = message.from_user.id
    manager = CompositeListenerManager.instance()
    
    subscriptions = manager.get_user_subscriptions(user_id)
    
    if not subscriptions:
        await message.answer(
            "ℹ️ У вас нет активных подписок на композитные алерты."
        )
        return
    
    alert_list = []
    for condition_id in subscriptions:
        listener = manager.get_listener_by_id(condition_id)
        if listener:
            expr_str = ast_to_string(listener._root)
            cooldown_info = f" (cooldown: {listener._cooldown}s)" if listener._cooldown > 0 else ""
            alert_list.append(f"• <code>{expr_str}</code>{cooldown_info}\n  ID: <code>{condition_id}</code>")
    
    response = f"📋 Ваши активные алерты ({len(alert_list)}):\n\n" + "\n\n".join(alert_list)
    
    await message.answer(response, parse_mode="HTML")
