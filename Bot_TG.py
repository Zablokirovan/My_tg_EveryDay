import asyncio
import os
import database

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime

import utilities
from payments import router as payments_router, PaymentAddState

load_dotenv()

TOKEN = os.getenv("TG_BOT_TOKEN")

dp = Dispatcher()
dp.include_router(payments_router)

button = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="Погода"),       KeyboardButton(text="Деньги")],
    [KeyboardButton(text="Календарь"),    KeyboardButton(text="Мои задачи")],
    [KeyboardButton(text="💳 Оплаты")],
], resize_keyboard=True)


class ReminderState(StatesGroup):
    waiting_for_note = State()


class NoteAction(CallbackData, prefix="note"):
    action:  str
    note_id: int


# ─── Вспомогательная функция: список задач ────────────────────────────────────

def _build_notes_message(notes) -> tuple[str, InlineKeyboardMarkup]:
    today = datetime.now().date()
    text = "📋 Твои задачи:\n\n"
    buttons = []
    for note in notes:
        note_date = note["date_complete"]
        status = "🔴" if note_date < today else ("🟡" if note_date == today else "🟢")
        text += f"{status} {note_date.strftime('%d.%m.%Y')} — {note['text']}\n"
        label = note["text"][:28] + ("…" if len(note["text"]) > 28 else "")
        buttons.append([InlineKeyboardButton(
            text=f"✅ {label}",
            callback_data=NoteAction(action="done", note_id=note["id"]).pack()
        )])
    text += "\n🟢 предстоит  🟡 сегодня  🔴 просрочено"
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


# ─── Команды ─────────────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    await database.record_data_user([user.id, user.username, user.first_name])
    await message.answer(
        f"👋 Привет, я Штрих!\n"
        f"📝 Записываю задачи, слежу за оплатами и напоминаю в 9:00\n\n"
        f"Вот что я умею:",
        reply_markup=button
    )


@dp.message(Command("list"))
async def echo_list(message: Message):
    await message.answer("Кнопочки ⏬", reply_markup=button)


# ─── Погода ──────────────────────────────────────────────────────────────────

@dp.message(F.text.lower() == "погода")
async def weather(message: Message):
    try:
        data = await utilities.weather()
    except Exception:
        await message.answer("⚠️ Не удалось получить данные о погоде. Попробуй позже.")
        return
    temp = data["main"]["temp"]
    if temp >= 30:       emoji = "🥵"
    elif temp >= 25:     emoji = "😓"
    elif 15 <= temp < 25: emoji = "🥴"
    elif temp <= -10:    emoji = "🥶"
    else:                emoji = "🙂"
    await message.answer(
        f"🌤 Погода в Алматы:\n"
        f"Температура: {temp} °C {emoji}\n"
        f"Ощущение: {data['main']['feels_like']} °C\n"
        f"Описание: {data['weather'][0]['description']}\n"
        f"💧 Влажность: {data['main']['humidity']} %\n"
        f"💨 Ветер: {data['wind']['speed']} м/с"
    )


# ─── Деньги ──────────────────────────────────────────────────────────────────

@dp.message(F.text.lower() == "деньги")
async def money(message: Message):
    try:
        data = await utilities.money()
    except Exception:
        await message.answer("⚠️ Не удалось получить курсы валют. Попробуй позже.")
        return
    await message.answer(
        f"💱 Курсы валют:\n"
        f"🇺🇸 USD — {data['USD']}₸\n"
        f"🇪🇺 EUR — {data['EUR']}₸\n"
        f"🇷🇺 RUB — {data['RUB']}₸"
    )


# ─── Общий обработчик календаря (заметки + оплаты) ───────────────────────────

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
    if not selected:
        return

    current_state = await state.get_state()

    if current_state == PaymentAddState.waiting_for_date.state:
        await state.update_data(payment_date=date.date() if hasattr(date, "date") else date)
        await state.set_state(PaymentAddState.waiting_for_amount)
        await callback.message.answer(
            f"📅 Дата оплаты: {date.strftime('%d.%m.%Y')}\n"
            f"💰 Введи плановую сумму в тенге:"
        )
    else:
        # По умолчанию — добавление заметки
        await state.update_data(selected_date=date.strftime("%d.%m.%Y"))
        await state.set_state(ReminderState.waiting_for_note)
        await callback.message.answer(
            f"✅ Дата выбрана: {date.strftime('%d.%m.%Y')}\n"
            f"Теперь введи, что нужно запланировать на этот день:"
        )

    await callback.answer()


# ─── Заметки: добавить ───────────────────────────────────────────────────────


@dp.message(ReminderState.waiting_for_note)
async def save_note(message: Message, state: FSMContext):
    user_data = await state.get_data()
    selected_date = datetime.strptime(user_data["selected_date"], "%d.%m.%Y").date()
    await database.writing_note_user([message.from_user.id, datetime.now(), message.text, selected_date])
    await message.answer(
        f"📝 Задача сохранена!\n"
        f"📅 Дата: {selected_date.strftime('%d.%m.%Y')}\n"
        f"📌 Дело: {message.text}"
    )
    await state.clear()


# ─── Заметки: просмотр и удаление ────────────────────────────────────────────

@dp.message(F.text.lower() == "мои задачи")
async def show_notes(message: Message):
    notes = await database.get_user_notes(message.from_user.id)
    if not notes:
        await message.answer(
            "📭 У тебя пока нет задач.\n\n"
            "Нажми 📅 Календарь чтобы добавить первую."
        )
        return
    text, keyboard = _build_notes_message(notes)
    await message.answer(text, reply_markup=keyboard)


@dp.callback_query(NoteAction.filter(F.action == "done"))
async def complete_note(callback: CallbackQuery, callback_data: NoteAction):
    await database.delete_user_note(callback_data.note_id)
    await callback.answer("✅ Выполнено!", show_alert=False)
    await callback.message.delete()

    notes = await database.get_user_notes(callback.from_user.id)
    if not notes:
        await callback.message.answer("🎉 Все задачи выполнены! Так держать!")
    else:
        text, keyboard = _build_notes_message(notes)
        await callback.message.answer(text, reply_markup=keyboard)


# ─── Утренние напоминания ─────────────────────────────────────────────────────

async def send_daily_reminders(bot: Bot):
    notes = await database.get_notes_due_today()
    if not notes:
        return
    user_notes: dict = {}
    for note in notes:
        user_notes.setdefault(note["user_id"], []).append(note["text"])
    for user_id, tasks in user_notes.items():
        task_list = "\n".join(f"• {t}" for t in tasks)
        try:
            await bot.send_message(user_id, f"🌅 Доброе утро! Задачи на сегодня:\n\n{task_list}")
        except Exception:
            pass


# ─── Запуск ───────────────────────────────────────────────────────────────────

async def main():
    bot = Bot(token=str(TOKEN))
    await database.create_pool()

    scheduler = AsyncIOScheduler(timezone="Asia/Almaty")
    scheduler.add_job(send_daily_reminders, "cron", hour=9, minute=0, args=[bot])
    scheduler.start()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
