import asyncio
from bot.bot import main as bot_main
from modules.price.tracker.logic import fetch_price_info

async def main():
    await bot_main()
    price_info = await fetch_price_info()
    print(price_info)

if __name__ == "__main__":
    asyncio.run(main())
