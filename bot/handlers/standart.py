from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

standart_router = Router()

@standart_router.message(Command("start"))
async def start_handler(message: Message) -> None:
    """Приветственное сообщение с полным списком команд бота.
    
    Args:
        message: Сообщение с командой start.
    """
    help_text = """
🤖 **Добро пожаловать в систему алертов!**

📋 **Все доступные команды:**

### 💰 **Отслеживание изменений цены:**
• `/price <процент> <интервал>` - подписка на изменение цены
  Пример: `/price 5 60` (уведомление при изменении >5% за 60 сек)

• `/get_all_price_listeners` - показать все подписки на цену

• `/unsubscribe_from_price_listener <ID>` - отписаться от конкретной подписки
  Пример: `/unsubscribe_from_price_listener 1234567890`

• `/unsubscribe_all_price` - отписаться от всех подписок на цену

### 📊 **Отслеживание абсолютного объёма:**
• `/volume_amount <сумма_USD> <интервал> <направление>` - подписка на объём
  Пример: `/volume_amount 10000000 300 >` (объём >10M USD за 300 сек)

• `/get_all_volume_amount_listeners` - показать все подписки на объём

• `/unsubscribe_from_volume_amount_listener <ID>` - отписаться от подписки
  Пример: `/unsubscribe_from_volume_amount_listener 1234567890`

• `/unsubscribe_all_volume_amount` - отписаться от всех подписок на объём

### 📈 **Отслеживание изменений объёма:**
• `/volume <процент> <интервал> <направление>` - подписка на изменение объёма
  Пример: `/volume 50 60 >` (увеличение объёма >50% за 60 сек)

• `/get_all_volume_listeners` - показать все подписки на изменения объёма

• `/unsubscribe_from_volume_listener <ID>` - отписаться от подписки
  Пример: `/unsubscribe_from_volume_listener 1234567890`

• `/unsubscribe_all_volume` - отписаться от всех подписок на объём

---
💡 **Направления сравнения:** `>` (больше) или `<` (меньше)
📝 **ID подписок** можно получить командой `get_all_*_listeners`
"""
    
    await message.answer(help_text)
