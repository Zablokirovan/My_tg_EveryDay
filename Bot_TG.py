import asyncio
import os
import database

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.state import default_state
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta

import calendar as cal_module

import utilities
from payments import router as payments_router, PaymentAddState

load_dotenv()

TOKEN = os.getenv("TG_BOT_TOKEN")

dp = Dispatcher()
dp.include_router(payments_router)

button = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🌤 Сводка на день")],
    [KeyboardButton(text="Календарь"),    KeyboardButton(text="Мои задачи")],
    [KeyboardButton(text="💳 Оплаты")],
], resize_keyboard=True)

cancel_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True
)


class ReminderState(StatesGroup):
    waiting_for_note   = State()
    waiting_for_repeat = State()


class NoteAction(CallbackData, prefix="note"):
    action:  str
    note_id: int


class RepeatAction(CallbackData, prefix="repeat"):
    value: str  # none / daily / weekly / monthly


REPEAT_LABELS = {
    "none":    "🚫 Без повтора",
    "daily":   "🔁 Ежедневно",
    "weekly":  "🔂 Еженедельно",
    "monthly": "🗓 Ежемесячно",
}

REPEAT_ICONS = {
    "daily":   " 🔁",
    "weekly":  " 🔂",
    "monthly": " 🗓",
}


def _next_repeat_date(current_date, repeat: str):
    if repeat == "daily":
        return current_date + timedelta(days=1)
    elif repeat == "weekly":
        return current_date + timedelta(weeks=1)
    elif repeat == "monthly":
        month = current_date.month % 12 + 1
        year  = current_date.year + (1 if current_date.month == 12 else 0)
        max_d = cal_module.monthrange(year, month)[1]
        return current_date.replace(year=year, month=month, day=min(current_date.day, max_d))
    return current_date


# ─── Вспомогательная функция: список задач ────────────────────────────────────

def _build_notes_message(notes) -> tuple[str, InlineKeyboardMarkup]:
    today = datetime.now().date()
    text = "📋 Твои задачи:\n\n"
    buttons = []
    for note in notes:
        note_date = note["date_complete"]
        status = "🔴" if note_date < today else ("🟡" if note_date == today else "🟢")
        repeat_icon = REPEAT_ICONS.get(note["repeat"] or "", "")
        text += f"{status} {note_date.strftime('%d.%m.%Y')} — {note['text']}{repeat_icon}\n"
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


@dp.message(Command("cancel"))
@dp.message(~StateFilter(default_state), F.text == "❌ Отмена")
async def cancel_action(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Отменено.", reply_markup=button)


# ─── Сводка на день ──────────────────────────────────────────────────────────

@dp.message(F.text == "🌤 Сводка на день")
async def daily_summary(message: Message):
    weather_data, money_data, errors = None, None, []

    try:
        weather_data = await utilities.weather()
    except Exception:
        errors.append("погода")

    try:
        money_data = await utilities.money()
    except Exception:
        errors.append("курсы валют")

    parts = []

    if weather_data:
        temp = weather_data["main"]["temp"]
        if temp >= 30:        emoji = "🥵"
        elif temp >= 25:      emoji = "😓"
        elif 15 <= temp < 25: emoji = "🥴"
        elif temp <= -10:     emoji = "🥶"
        else:                 emoji = "🙂"
        parts.append(
            f"🌤 Погода в Алматы:\n"
            f"Температура: {temp} °C {emoji}\n"
            f"Ощущение: {weather_data['main']['feels_like']} °C\n"
            f"Описание: {weather_data['weather'][0]['description']}\n"
            f"💧 Влажность: {weather_data['main']['humidity']} %\n"
            f"💨 Ветер: {weather_data['wind']['speed']} м/с"
        )

    if money_data:
        parts.append(
            f"💱 Курсы валют:\n"
            f"🇺🇸 USD — {money_data['USD']}₸\n"
            f"🇪🇺 EUR — {money_data['EUR']}₸\n"
            f"🇷🇺 RUB — {money_data['RUB']}₸"
        )

    if errors:
        parts.append(f"⚠️ Не удалось получить: {', '.join(errors)}.")

    await message.answer("\n\n".join(parts) if parts else "⚠️ Данные недоступны. Попробуй позже.")


# ─── Общий обработчик календаря (заметки + оплаты) ───────────────────────────

@dp.message(F.text.lower() == "календарь")
async def cmd_calendar(message: Message):
    await message.answer(
        "📅 Выбери дату:",
        reply_markup=await SimpleCalendar().start_calendar()
    )


def _next_occurrence(day: int):
    """Вычисляет следующую дату с заданным числом месяца."""
    from datetime import date as date_type
    today = date_type.today()
    try:
        candidate = today.replace(day=day)
        if candidate >= today:
            return candidate
    except ValueError:
        pass
    if today.month == 12:
        y, m = today.year + 1, 1
    else:
        y, m = today.year, today.month + 1
    max_d = cal_module.monthrange(y, m)[1]
    return date_type(y, m, min(day, max_d))


@dp.callback_query(SimpleCalendarCallback.filter())
async def process_calendar(
        callback: CallbackQuery,
        callback_data: SimpleCalendarCallback,
        state: FSMContext):
    selected, date = await SimpleCalendar().process_selection(callback, callback_data)
    if not selected:
        try:
            await callback.answer()
        except Exception:
            pass
        return

    current_state = await state.get_state()

    if current_state == PaymentAddState.waiting_for_date.state:
        day = date.day
        next_date = _next_occurrence(day)
        fsm_data = await state.get_data()
        await database.add_payment(
            user_id=callback.from_user.id,
            name=fsm_data["payment_name"],
            category="other",
            planned_amount=fsm_data["payment_amount"],
            planned_date=next_date,
            day_of_month=day,
        )
        await state.clear()
        await callback.message.answer(
            f"✅ Ежемесячный платёж добавлен!\n\n"
            f"📌 <b>{fsm_data['payment_name']}</b>\n"
            f"📅 Каждого {day}-го числа\n"
            f"💰 {fsm_data['payment_amount']:,.0f}₸\n"
            f"⏭ Ближайшая дата: {next_date.strftime('%d.%m.%Y')}",
            parse_mode="HTML"
        )
    else:
        # По умолчанию — добавление заметки
        await state.update_data(selected_date=date.strftime("%d.%m.%Y"))
        await state.set_state(ReminderState.waiting_for_note)
        await callback.message.answer(
            f"✅ Дата выбрана: {date.strftime('%d.%m.%Y')}\n"
            f"Теперь введи, что нужно запланировать на этот день:",
            reply_markup=cancel_keyboard
        )

    await callback.answer()


# ─── Заметки: добавить ───────────────────────────────────────────────────────


@dp.message(ReminderState.waiting_for_note)
async def save_note(message: Message, state: FSMContext):
    await state.update_data(note_text=message.text)
    await state.set_state(ReminderState.waiting_for_repeat)
    repeat_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚫 Без повтора",   callback_data=RepeatAction(value="none").pack()),
            InlineKeyboardButton(text="🔁 Ежедневно",     callback_data=RepeatAction(value="daily").pack()),
        ],
        [
            InlineKeyboardButton(text="🔂 Еженедельно",   callback_data=RepeatAction(value="weekly").pack()),
            InlineKeyboardButton(text="🗓 Ежемесячно",    callback_data=RepeatAction(value="monthly").pack()),
        ],
    ])
    await message.answer("🔄 Задача повторяется?", reply_markup=repeat_kb)


@dp.callback_query(RepeatAction.filter())
async def choose_repeat(callback: CallbackQuery, callback_data: RepeatAction, state: FSMContext):
    data = await state.get_data()
    selected_date = datetime.strptime(data["selected_date"], "%d.%m.%Y").date()
    repeat = callback_data.value if callback_data.value != "none" else None
    await database.writing_note_user(
        user_id=callback.from_user.id,
        date_create=datetime.now(),
        text=data["note_text"],
        date_complete=selected_date,
        repeat=repeat,
    )
    repeat_label = REPEAT_LABELS.get(callback_data.value, "🚫 Без повтора")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"📝 Задача сохранена!\n"
        f"📅 Дата: {selected_date.strftime('%d.%m.%Y')}\n"
        f"📌 Дело: {data['note_text']}\n"
        f"🔄 Повтор: {repeat_label}",
        reply_markup=button
    )
    await state.clear()
    await callback.answer()


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
    note = await database.get_note_by_id(callback_data.note_id)
    await database.delete_user_note(callback_data.note_id)

    if note and note["repeat"]:
        next_date = _next_repeat_date(note["date_complete"], note["repeat"])
        await database.writing_note_user(
            user_id=note["user_id"],
            date_create=datetime.now(),
            text=note["text"],
            date_complete=next_date,
            repeat=note["repeat"],
        )
        await callback.answer(
            f"✅ Выполнено! Следующий повтор: {next_date.strftime('%d.%m.%Y')}",
            show_alert=True
        )
    else:
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
    from datetime import date as date_type
    tomorrow = date_type.today() + timedelta(days=1)

    today_notes    = await database.get_notes_due_today()
    tomorrow_notes = await database.get_notes_due_date(tomorrow)

    today_by_user:    dict = {}
    tomorrow_by_user: dict = {}
    for n in today_notes:
        today_by_user.setdefault(n["user_id"], []).append(n["text"])
    for n in tomorrow_notes:
        tomorrow_by_user.setdefault(n["user_id"], []).append(n["text"])

    all_users = set(today_by_user) | set(tomorrow_by_user)
    if not all_users:
        return

    for user_id in all_users:
        parts = ["🌅 Доброе утро!\n"]

        today_tasks = today_by_user.get(user_id)
        if today_tasks:
            parts.append("📋 Задачи на сегодня:")
            parts.extend(f"  • {t}" for t in today_tasks)
        else:
            parts.append("✅ Задач на сегодня нет!")

        tomorrow_tasks = tomorrow_by_user.get(user_id)
        if tomorrow_tasks:
            parts.append(f"\n📅 Завтра ({tomorrow.strftime('%d.%m')}):")
            parts.extend(f"  • {t}" for t in tomorrow_tasks)

        try:
            await bot.send_message(user_id, "\n".join(parts))
        except Exception:
            pass


# ─── Запуск ───────────────────────────────────────────────────────────────────

async def main():
    bot = Bot(token=str(TOKEN))
    await database.create_pool()

    scheduler = AsyncIOScheduler(timezone="Asia/Almaty")
    for hour in (9, 12, 15, 18, 20):
        scheduler.add_job(send_daily_reminders, "cron", hour=hour, minute=0, args=[bot])
    scheduler.start()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
