import httpx
from typing import TypedDict

PRICE_API_URL = "https://fapi.binance.com/fapi/v1/ticker/price"
TICKER_BLACKLIST = ["USDC"]


class PriceInfo(TypedDict):
    symbol: str
    price: str
    time: int

async def fetch_price_info() -> list[PriceInfo]:
    """Асинхронно получает цены с Binance и отбрасывает пары из черного списка.

    Returns:
        list[PriceInfo]: Список словарей с полями:
            - symbol (str): Название торговой пары
            - price (str): Цена в виде строки
            - time (int): Временная метка (UNIX time в миллисекундах)
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(PRICE_API_URL)
        data = resp.json()
        lower_blacklist = [ticker.lower() for ticker in TICKER_BLACKLIST]
        return [
            i for i in data
            if not any(blacklisted in i["symbol"].lower() for blacklisted in lower_blacklist)
        ]