import asyncio
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=True)

from bot.bot import main as bot_main
from modules.price.price import main as price_main
from modules.volume_change.volume import main as volume_change_main
from modules.oi.oi import main as oi_main

async def main():
    await asyncio.gather(bot_main(), price_main(), volume_change_main(), oi_main())

if __name__ == "__main__":
    asyncio.run(main())

