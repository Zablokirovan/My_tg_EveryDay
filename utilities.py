import requests
import os
from dotenv import load_dotenv

load_dotenv()

def weather():
     response = requests.get(os.getenv("WEATHER_URL"))

     print(response.json())
     return response.json()