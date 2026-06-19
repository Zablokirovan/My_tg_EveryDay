from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.filters.callback_data import CallbackData
from aiogram_calendar import SimpleCalendar
from datetime import date, datetime, timedelta

import database
from keyboards import button_female

router = Router()

DEFAULT_CYCLE_DAYS = 28


class CycleAction(CallbackData, prefix="cycle"):
    action: str


def _predict(history: list) -> tuple[date, int]:
    """Возвращает (predicted_date, avg_length)."""
    dates = sorted([r["start_date"] for r in history])
    if len(dates) >= 2:
        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        avg = round(sum(gaps) / len(gaps))
    else:
        avg = DEFAULT_CYCLE_DAYS
    return dates[-1] + timedelta(days=avg), avg


# ─── Главное меню ─────────────────────────────────────────────────────────────

@router.message(F.text == "🌸 Цикл")
async def cycle_menu(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 Отметить начало", callback_data=CycleAction(action="mark").pack()),
            InlineKeyboardButton(text="🔮 Прогноз",         callback_data=CycleAction(action="forecast").pack()),
        ],
        [
            InlineKeyboardButton(text="📋 История",         callback_data=CycleAction(action="history").pack()),
        ],
    ])
    await message.answer("🌸 Трекер цикла:", reply_markup=kb)


# ─── Отметить начало ──────────────────────────────────────────────────────────

@router.callback_query(CycleAction.filter(F.action == "mark"))
async def cb_mark(callback: CallbackQuery):
    today = date.today()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"✅ Сегодня ({today.strftime('%d.%m.%Y')})",
                callback_data=CycleAction(action=f"save_{today.isoformat()}").pack()
            ),
        ],
        [
            InlineKeyboardButton(text="📆 Выбрать дату", callback_data=CycleAction(action="pick_date").pack()),
        ],
    ])
    await callback.message.answer("📅 Когда начался цикл?", reply_markup=kb)
    await callback.answer()


@router.callback_query(CycleAction.filter(F.action == "pick_date"))
async def cb_pick_date(callback: CallbackQuery, state: FSMContext):
    await state.update_data(cycle_awaiting_date=True)
    await callback.message.answer(
        "📆 Выбери дату начала цикла:",
        reply_markup=await SimpleCalendar().start_calendar()
    )
    await callback.answer()


@router.callback_query(CycleAction.filter(F.action.startswith("save_")))
async def cb_save_today(callback: CallbackQuery, callback_data: CycleAction):
    date_str = callback_data.action.replace("save_", "")
    start = date.fromisoformat(date_str)
    await database.add_cycle(callback.from_user.id, start)
    history = await database.get_cycle_history(callback.from_user.id)
    predicted, avg = _predict(history)
    await callback.message.answer(
        f"✅ Начало цикла отмечено: <b>{start.strftime('%d.%m.%Y')}</b>\n\n"
        f"🔮 Следующий ожидается: <b>{predicted.strftime('%d.%m.%Y')}</b>\n"
        f"📏 Средняя длина цикла: <b>{avg} дней</b>",
        parse_mode="HTML",
        reply_markup=button_female
    )
    await callback.answer()


# ─── Прогноз ──────────────────────────────────────────────────────────────────

@router.callback_query(CycleAction.filter(F.action == "forecast"))
async def cb_forecast(callback: CallbackQuery):
    history = await database.get_cycle_history(callback.from_user.id)
    if not history:
        await callback.message.answer("📭 Нет данных. Сначала отметь начало цикла.")
        await callback.answer()
        return

    predicted, avg = _predict(history)
    today = date.today()
    days_left = (predicted - today).days

    if days_left > 0:
        countdown = f"через <b>{days_left} дн.</b>"
    elif days_left == 0:
        countdown = "<b>сегодня</b>"
    else:
        countdown = f"<b>{abs(days_left)} дн. назад</b> (данные устарели?)"

    last = history[0]["start_date"]
    phase_day = (today - last).days + 1

    await callback.message.answer(
        f"🔮 <b>Прогноз цикла</b>\n\n"
        f"🗓 Последний цикл: {last.strftime('%d.%m.%Y')}\n"
        f"📅 День цикла сейчас: <b>{phase_day}</b>\n"
        f"⏭ Следующий: <b>{predicted.strftime('%d.%m.%Y')}</b> — {countdown}\n"
        f"📏 Средняя длина: <b>{avg} дней</b>",
        parse_mode="HTML"
    )
    await callback.answer()


# ─── История ──────────────────────────────────────────────────────────────────

@router.callback_query(CycleAction.filter(F.action == "history"))
async def cb_history(callback: CallbackQuery):
    history = await database.get_cycle_history(callback.from_user.id, limit=6)
    if not history:
        await callback.message.answer("📭 История пуста.")
        await callback.answer()
        return

    text = "📋 <b>История циклов:</b>\n\n"
    dates = sorted([r["start_date"] for r in history])
    for i, d in enumerate(reversed(dates)):
        if i < len(dates) - 1:
            length = (dates[-(i + 1)] - dates[-(i + 2)]).days
            text += f"• {d.strftime('%d.%m.%Y')} — {length} дней\n"
        else:
            text += f"• {d.strftime('%d.%m.%Y')}\n"

    if len(dates) >= 2:
        _, avg = _predict(history)
        text += f"\n📏 Средняя длина: <b>{avg} дней</b>"

    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()
