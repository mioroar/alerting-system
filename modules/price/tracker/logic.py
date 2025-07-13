import httpx

from modules.price.config import PriceInfo, PRICE_API_URL, TICKER_BLACKLIST

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