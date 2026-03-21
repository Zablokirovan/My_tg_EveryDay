import asyncio
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

load_dotenv()
TOKEN = os.getenv("TG_BOT_TOKEN")

dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer("🤖 Куку ляля чичи гага\nЯ BOT|Календарь\n Буду записывать таски и информировать тебя")


@dp.message()
async def echo_message(message: Message):
    await message.answer(f"Ты написал: {message.text}")


async def main():
    bot = Bot(token=str(TOKEN))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())