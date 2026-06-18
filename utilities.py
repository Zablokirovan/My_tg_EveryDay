import aiohttp
import os
from dotenv import load_dotenv

load_dotenv()


async def weather():
    async with aiohttp.ClientSession() as session:
        async with session.get(os.getenv("WEATHER_URL")) as response:
            response.raise_for_status()
            return await response.json()


async def money():
    urls = {
        "USD": os.getenv("MONEY_USD"),
        "EUR": os.getenv("MONEY_EUR"),
        "RUB": os.getenv("MONEY_RUB"),
    }
    result = {}
    async with aiohttp.ClientSession() as session:
        for currency, url in urls.items():
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                result[currency] = round(data["rates"]["KZT"], 2)
    return result
