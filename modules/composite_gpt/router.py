# coding: utf-8
"""
Aiogram-роутер: команды
    /alert <выражение>
    /get_all_alerts
    /unsubscribe_alert <ID>
    /unsubscribe_all_alerts
"""
import html as html_utils
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode
from .listener.manager import get_composite_listener_manager

composite_router = Router()


# ---------- /alert <expr> ----------
@composite_router.message(Command("alert"))
async def alert_handler(message: Message):
    expr = message.text[len("/alert"):].strip()
    if not expr:
        await message.answer("❗ Пример: /alert (price > 5% 300 & volume > 1e6 600) @3600")
        return
    try:
        mgr = await get_composite_listener_manager()
        listener = await mgr.add_listener(expr, message.from_user.id)
        await message.answer(
            f"✅ Подписка создана. ID: <code>{listener.condition_id}</code>\n"
            f"Интервал проверки: {listener.interval} с.",
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:
        await message.answer(f"Ошибка в выражении: <code>{exc}</code>", parse_mode=ParseMode.HTML)


# ---------- /get_all_alerts ----------
@composite_router.message(Command("get_all_alerts"))
async def all_alerts_handler(message: Message):
    mgr = await get_composite_listener_manager()
    listeners = mgr.get_all_user_listeners(message.from_user.id)

    if not listeners:
        await message.answer("У вас нет композитных подписок.")
        return

    parts = ["<b>⚡ Ваши композит-алерты:</b>"]
    for l in listeners:
        parts.append(
            f"• {html_utils.escape(l.expression)}\n"
            f"  ID: <code>{l.condition_id}</code>"
        )

    await message.answer("\n\n".join(parts), parse_mode=ParseMode.HTML)


# ---------- /unsubscribe_alert <ID> ----------
@composite_router.message(Command("unsubscribe_alert"))
async def unsubs_one(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Пример: /unsubscribe_alert 123456789")
        return
    cid = parts[1]
    mgr = await get_composite_listener_manager()
    await mgr.remove_listener(cid, message.from_user.id)
    await message.answer(f"Отписка от алерта <code>{cid}</code> выполнена.", parse_mode=ParseMode.HTML)


# ---------- /unsubscribe_all_alerts ----------
@composite_router.message(Command("unsubscribe_all_alerts"))
async def unsubs_all(message: Message):
    mgr = await get_composite_listener_manager()
    mgr.unsubscribe_user_from_all(message.from_user.id)
    await message.answer("Все композит-подписки удалены.")
