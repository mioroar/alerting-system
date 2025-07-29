import asyncio
import datetime as dt
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from modules.composite.utils import parse_expression
from modules.composite.manager import CompositeListenerManager

alert_router: Router = Router()

async def composite_loop(base_step: int = 5) -> None:
    mgr = CompositeListenerManager.instance()
    while True:
        print("[LOOP]", dt.datetime.utcnow().isoformat(timespec="seconds"))
        try:
            await mgr.tick()
        except Exception as exc:
            import traceback, sys
            print("[ERR] composite tick failed:", exc, file=sys.stderr)
            traceback.print_exc()
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
    except Exception as exc:  # LarkError | ValueError
        await message.answer(f"Синтаксическая ошибка: <code>{exc}</code>", parse_mode="HTML")
        return

    manager = CompositeListenerManager.instance()
    await manager.add_listener(ast, user_id)
    print("[MAN]", len(manager._listeners), "comp‑listeners total")

    await message.answer(
        "✅ Композитный алерт зарегистрирован и начнёт проверяться в течение нескольких секунд."
    )
