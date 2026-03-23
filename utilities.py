import requests
import os
from dotenv import load_dotenv

load_dotenv()

def weather():
     response = requests.get(os.getenv("WEATHER_URL"))

     print(response.json())
     return response.json()


def money():
    urls = {
        "USD": os.getenv("MONEY_USD"),
        "EUR": os.getenv("MONEY_EUR"),
        "RUB": os.getenv("MONEY_RUB"),
    }
    result = {}
    for currency, url in urls.items():

        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        result[currency] = round(data["rates"]["KZT"], 2)

    return result