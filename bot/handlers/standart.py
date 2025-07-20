from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode

standart_router = Router()

@standart_router.message(Command("start"))
async def start_handler(message: Message) -> None:
    """Приветственное сообщение с полным списком команд бота.
    
    Args:
        message: Сообщение с командой start.
    """
    help_text = """
🤖 <b>Добро пожаловать в систему алертов!</b>

📋 <b>Все доступные команды:</b>

<b>💰 Отслеживание изменений цены:</b>
• <code>/price &lt;процент&gt; &lt;интервал&gt;</code> - подписка на изменение цены
  Пример: <code>/price 5 60</code> (уведомление при изменении >5% за 60 сек)

• <code>/get_all_price_listeners</code> - показать все подписки на цену

• <code>/unsubscribe_from_price_listener &lt;ID&gt;</code> - отписаться от конкретной подписки
  Пример: <code>/unsubscribe_from_price_listener 1234567890</code>

• <code>/unsubscribe_all_price</code> - отписаться от всех подписок на цену

<b>📊 Отслеживание абсолютного объёма:</b>
• <code>/volume_amount &lt;сумма_USD&gt; &lt;интервал&gt; &lt;направление&gt;</code> - подписка на объём
  Пример: <code>/volume_amount 10000000 300 ></code> (объём >10M USD за 300 сек)

• <code>/get_all_volume_amount_listeners</code> - показать все подписки на объём

• <code>/unsubscribe_from_volume_amount_listener &lt;ID&gt;</code> - отписаться от подписки
  Пример: <code>/unsubscribe_from_volume_amount_listener 1234567890</code>

• <code>/unsubscribe_all_volume_amount</code> - отписаться от всех подписок на объём

<b>📈 Отслеживание изменений объёма:</b>
• <code>/volume &lt;процент&gt; &lt;интервал&gt; &lt;направление&gt;</code> - подписка на изменение объёма
  Пример: <code>/volume 50 60 ></code> (увеличение объёма >50% за 60 сек)

• <code>/get_all_volume_listeners</code> - показать все подписки на изменения объёма

• <code>/unsubscribe_from_volume_listener &lt;ID&gt;</code> - отписаться от подписки
  Пример: <code>/unsubscribe_from_volume_listener 1234567890</code>

• <code>/unsubscribe_all_volume</code> - отписаться от всех подписок на объём

<b>📋 Общие команды:</b>
• <code>/get_all_listeners</code> - показать все активные подписки

---
💡 <b>Направления сравнения:</b> <code>></code> (больше) или <code>&lt;</code> (меньше)
📝 <b>ID подписок</b> можно получить командой <code>get_all_*_listeners</code>
"""
    
    await message.answer(help_text, parse_mode=ParseMode.HTML)
