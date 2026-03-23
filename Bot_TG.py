import asyncio
import os
import utilities
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

load_dotenv()

TOKEN = os.getenv("TG_BOT_TOKEN")

dp = Dispatcher()

button = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="Погода")],
    [KeyboardButton(text="Деньги")]
],resize_keyboard=True)


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer("👋Привет, я Штрих\n📝Буду записывать таски и информировать тебя\n Вот что я пока умею",
                         reply_markup=button)


@dp.message(Command("list"))
async def echo_list(message: Message):
        await message.answer(f"Кнопочки ⏬", reply_markup=button)


@dp.message(F.text.lower() == "погода")
async def weather(message: Message):
    data = utilities.weather()
    temp = data['main']['temp']
    if temp >= 30:
        emoji = "🥵"
    elif temp >= 25:
        emoji = "😓"
    elif 15 <= temp < 25:
        emoji = "🥴"
    elif temp <= -10:
        emoji = "🥶"
    else:
        emoji = "🙂"
    await message.answer(f'🌤 Погода в Алматы:\nТемпература: {data['main']['temp']} °C {emoji}\n'
                         f'Ощущение: {data['main']['feels_like']} °C\n'
                         f'Описание: {data['weather'][0]['description']} \n'
                         f'💧Влажность: {data['main']['humidity']} %\n'
                         f'💨Ветер: {data['wind']['speed']} м/с')


@dp.message(F.text.lower() == "деньги")
async def money(message: Message):
    data = utilities.money()
    await message.answer(f"💱 Курсы валют:\n"
                         f"🇺🇸(USD) - {data["USD"]}₸\n"
                         f"🇪🇺(EUR) - {data["EUR"]}₸\n"
                         f"🇷🇺(RUB) -{data["RUB"]}₸")


async def main():
    bot = Bot(token=str(TOKEN))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())