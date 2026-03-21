import asyncio
import os
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
    await message.answer('Солнце ебать')


@dp.message(F.text.lower() == "деньги")
async def money(message: Message):
    await message.answer('Нищета')


async def main():
    bot = Bot(token=str(TOKEN))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())