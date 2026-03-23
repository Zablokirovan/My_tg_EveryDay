import asyncio
import os
import database

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery
from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

import utilities

load_dotenv()

TOKEN = os.getenv("TG_BOT_TOKEN")

dp = Dispatcher()

button = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="Погода")],
    [KeyboardButton(text="Деньги")],
    [KeyboardButton(text="Календарь")]
],resize_keyboard=True)


class ReminderState(StatesGroup):
    waiting_for_note = State()


@dp.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    data = [
        user.id,
        user.username,
        user.first_name
    ]
    print(data)
    await database.record_data_user(data)
    await message.answer(f"👋Привет, я Штрих\n📝Буду записывать таски и информировать тебя\n Вот что я пока умею",
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

# Для работы календаря
@dp.message(F.text.lower() == "календарь")
async def cmd_calendar(message: Message):
    await message.answer(
        "📅 Выбери дату:",
        reply_markup=await SimpleCalendar().start_calendar()
    )


@dp.callback_query(SimpleCalendarCallback.filter())
async def process_calendar(
        callback: CallbackQuery,
        callback_data: SimpleCalendarCallback,
        state: FSMContext):

    selected, date = await SimpleCalendar().process_selection(callback, callback_data)

    await state.update_data(selected_date=date.strftime("%d.%m.%Y"))
    await state.set_state(ReminderState.waiting_for_note)

    await callback.message.answer(
        f"✅ Дата выбрана: {date.strftime('%d.%m.%Y')}\n"
        f"Теперь введи, что нужно запланировать на этот день:"
    )

    await callback.answer()


@dp.message(ReminderState.waiting_for_note)
async def save_note(message: Message, state: FSMContext):
    user_data = await state.get_data()
    selected_date = user_data.get("selected_date")
    note_text = message.text

    await message.answer(
        f"📝 Заметка сохранена:\n"
        f"Дата: {selected_date}\n"
        f"Дело: {note_text}"
    )

    await state.clear()


async def main():
    bot = Bot(token=str(TOKEN))
    await database.create_pool()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())