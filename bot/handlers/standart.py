from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode

standart_router = Router()


@standart_router.message(Command("start"))
async def start_handler(message: Message) -> None:
    """Приветственное сообщение со списком команд бота."""
    help_text = """
🤖 <b>Добро пожаловать в систему алертов!</b>

📋 <b>Все доступные команды:</b>

<b>💰 Отслеживание изменений цены:</b>
• <code>/price [&gt; или &lt;] [процент] [интервал_сек]</code> — подписка на изменение цены  
  Пример: <code>/price &gt; 5 60</code> (уведомление при изменении цены &gt; 5 % за 60 сек)

• <code>/get_all_price_listeners</code> — показать все подписки на цену  
• <code>/unsubscribe_from_price_listener [ID]</code> — отписаться от конкретной подписки  
  Пример: <code>/unsubscribe_from_price_listener 1234567890</code>  
• <code>/unsubscribe_all_price</code> — отписаться от всех подписок на цену

<b>📊 Отслеживание абсолютного объёма:</b>
• <code>/volume_amount [&gt; или &lt;] [сумма_USD] [интервал_сек]</code> — подписка на объём  
  Пример: <code>/volume_amount &gt; 10000000 300</code> (объём &gt; 10 M USD за 300 сек)

• <code>/get_all_volume_amount_listeners</code> — показать все подписки на объём  
• <code>/unsubscribe_from_volume_amount_listener [ID]</code> — отписаться от подписки  
  Пример: <code>/unsubscribe_from_volume_amount_listener 1234567890</code>  
• <code>/unsubscribe_all_volume_amount</code> — отписаться от всех подписок на объём

<b>📈 Отслеживание изменений объёма:</b>
• <code>/volume [&gt; или &lt;] [процент] [интервал_сек]</code> — подписка на изменение объёма  
  Пример: <code>/volume &gt; 50 60</code> (увеличение объёма &gt; 50 % за 60 сек)

• <code>/get_all_volume_listeners</code> — показать все подписки на изменения объёма  
• <code>/unsubscribe_from_volume_listener [ID]</code> — отписаться от подписки  
  Пример: <code>/unsubscribe_from_volume_listener 1234567890</code>  
• <code>/unsubscribe_all_volume</code> — отписаться от всех подписок на объём

<b>📈 Отслеживание изменений OI:</b>
• <code>/oi [&gt; или &lt;] [процент]</code> — подписка на изменение OI  
  Пример: <code>/oi &gt; 50</code> (увеличение OI &gt; 50 % от медианы)

• <code>/get_all_oi_listeners</code> — показать все подписки на изменения OI  
• <code>/unsubscribe_all_oi</code> — отписаться от всех подписок на OI

<b>📅 Отслеживание funding‑ставки:</b>
• <code>/funding [&gt; или &lt;] [процент] [сек_до_расчёта]</code>
  Пример: <code>/funding &gt; 2 600</code>
• <code>/get_all_funding_listeners</code>
• <code>/unsubscribe_from_funding_listener [ID]</code>
• <code>/unsubscribe_all_funding</code>

<b>📋 Общие команды:</b>
• <code>/get_all_listeners</code> — показать все активные подписки

---
💡 <b>Направления сравнения:</b> <code>&gt;</code> (больше) или <code>&lt;</code> (меньше)  
📝 <b>ID подписок</b> можно получить командой <code>/get_all_*_listeners</code>
"""

    await message.answer(help_text, parse_mode=ParseMode.HTML)
