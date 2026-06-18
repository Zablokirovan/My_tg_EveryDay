from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters.callback_data import CallbackData
from aiogram_calendar import SimpleCalendar
from datetime import datetime

import database

router = Router()

CATEGORIES: dict[str, str] = {
    "housing":       "🏠 Жильё",
    "internet":      "🌐 Интернет/Связь",
    "transport":     "🚗 Транспорт",
    "food":          "🛒 Продукты",
    "health":        "💊 Здоровье",
    "entertainment": "🎮 Развлечения",
    "other":         "📦 Другое",
}


# ─── FSM ─────────────────────────────────────────────────────────────────────

class PaymentAddState(StatesGroup):
    waiting_for_name     = State()
    waiting_for_category = State()
    waiting_for_date     = State()   # calendar — обрабатывается в Bot_TG.py
    waiting_for_amount   = State()


class PaymentPayState(StatesGroup):
    waiting_for_paid_amount = State()


# ─── Callback Data ────────────────────────────────────────────────────────────

class PayAction(CallbackData, prefix="payact"):
    action:     str
    payment_id: int = 0


class CatSelect(CallbackData, prefix="catsel"):
    category: str


# ─── Вспомогательные функции ──────────────────────────────────────────────────

def _unpaid_keyboard(payments) -> tuple[str, InlineKeyboardMarkup]:
    today = datetime.now().date()
    text = "💳 Запланированные оплаты:\n\n"
    buttons = []
    for p in payments:
        d = p["planned_date"]
        status = "🔴" if d < today else ("🟡" if d == today else "🟢")
        cat = CATEGORIES.get(p["category"], "📦 Другое")
        text += f"{status} {d.strftime('%d.%m.%Y')} | {cat} | {p['name']}: {p['planned_amount']:,.0f}₸\n"
        name_short = p["name"][:18] + ("…" if len(p["name"]) > 18 else "")
        buttons.append([
            InlineKeyboardButton(
                text=f"✅ {name_short} ({p['planned_amount']:,.0f}₸)",
                callback_data=PayAction(action="pay", payment_id=p["id"]).pack()
            ),
            InlineKeyboardButton(
                text="🗑",
                callback_data=PayAction(action="delete", payment_id=p["id"]).pack()
            ),
        ])
    text += "\n🟢 предстоит  🟡 сегодня  🔴 просрочено"
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


# ─── Главное меню оплат ───────────────────────────────────────────────────────

@router.message(F.text.lower() == "💳 оплаты")
async def payments_menu(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💰 Внести оплату",  callback_data=PayAction(action="list").pack()),
            InlineKeyboardButton(text="➕ Добавить",       callback_data=PayAction(action="add").pack()),
        ],
        [
            InlineKeyboardButton(text="📊 Отчёт за месяц", callback_data=PayAction(action="report").pack()),
        ],
    ])
    await message.answer("💳 Планировщик оплат:", reply_markup=kb)


# ─── Добавить оплату ──────────────────────────────────────────────────────────

@router.callback_query(PayAction.filter(F.action == "add"))
async def cb_add_payment(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PaymentAddState.waiting_for_name)
    await callback.message.answer(
        "📝 Введи название оплаты:\n"
        "<i>например: Аренда, Кредит, Netflix, Коммуналка</i>",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(PaymentAddState.waiting_for_name)
async def got_payment_name(message: Message, state: FSMContext):
    await state.update_data(payment_name=message.text.strip())
    await state.set_state(PaymentAddState.waiting_for_category)

    rows, row = [], []
    for key, label in CATEGORIES.items():
        row.append(InlineKeyboardButton(text=label, callback_data=CatSelect(category=key).pack()))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    await message.answer("📂 Выбери категорию:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(CatSelect.filter(), PaymentAddState.waiting_for_category)
async def got_payment_category(callback: CallbackQuery, callback_data: CatSelect, state: FSMContext):
    await state.update_data(payment_category=callback_data.category)
    await state.set_state(PaymentAddState.waiting_for_date)
    await callback.message.answer(
        "📅 Выбери дату оплаты:",
        reply_markup=await SimpleCalendar().start_calendar()
    )
    await callback.answer()


# waiting_for_date обрабатывается в Bot_TG.py (общий calendar handler)


@router.message(PaymentAddState.waiting_for_amount)
async def got_payment_amount(message: Message, state: FSMContext):
    raw = message.text.strip().replace(",", ".").replace(" ", "").replace("\u202f", "")
    try:
        amount = float(raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи сумму числом, например: <b>15000</b>", parse_mode="HTML")
        return

    data = await state.get_data()
    await database.add_payment(
        user_id=message.from_user.id,
        name=data["payment_name"],
        category=data["payment_category"],
        planned_amount=amount,
        planned_date=data["payment_date"],
    )
    cat_label = CATEGORIES.get(data["payment_category"], "📦 Другое")
    await message.answer(
        f"✅ Оплата добавлена!\n\n"
        f"📌 <b>{data['payment_name']}</b>\n"
        f"📂 {cat_label}\n"
        f"📅 {data['payment_date'].strftime('%d.%m.%Y')}\n"
        f"💰 {amount:,.0f}₸",
        parse_mode="HTML"
    )
    await state.clear()


# ─── Список неоплаченных ──────────────────────────────────────────────────────

@router.callback_query(PayAction.filter(F.action == "list"))
async def cb_unpaid_list(callback: CallbackQuery):
    payments = await database.get_unpaid_payments(callback.from_user.id)
    if not payments:
        await callback.message.answer("✅ Нет запланированных оплат! Всё оплачено.")
        await callback.answer()
        return
    text, keyboard = _unpaid_keyboard(payments)
    await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


# ─── Внести оплату ────────────────────────────────────────────────────────────

@router.callback_query(PayAction.filter(F.action == "pay"))
async def cb_start_pay(callback: CallbackQuery, callback_data: PayAction, state: FSMContext):
    payment = await database.get_payment_by_id(callback_data.payment_id)
    if not payment:
        await callback.answer("Оплата не найдена", show_alert=True)
        return

    await state.set_state(PaymentPayState.waiting_for_paid_amount)
    await state.update_data(paying_id=callback_data.payment_id, planned_amount=float(payment["planned_amount"]))

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=f"= {payment['planned_amount']:,.0f}₸  (плановая сумма)",
            callback_data=PayAction(action="confirm_planned", payment_id=callback_data.payment_id).pack()
        )
    ]])
    await callback.message.answer(
        f"💳 <b>{payment['name']}</b>\n"
        f"Плановая: {payment['planned_amount']:,.0f}₸\n\n"
        f"Введи фактическую сумму или нажми кнопку:",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(PaymentPayState.waiting_for_paid_amount)
async def got_paid_amount(message: Message, state: FSMContext):
    raw = message.text.strip().replace(",", ".").replace(" ", "").replace("\u202f", "")
    try:
        amount = float(raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи сумму числом, например: <b>15000</b>", parse_mode="HTML")
        return

    data = await state.get_data()
    await database.mark_payment_paid(data["paying_id"], amount)
    diff = amount - data["planned_amount"]
    diff_str = f"  ({'+' if diff >= 0 else ''}{diff:,.0f}₸ от плана)" if diff != 0 else ""
    await message.answer(f"✅ Оплата записана: <b>{amount:,.0f}₸</b>{diff_str}", parse_mode="HTML")
    await state.clear()


@router.callback_query(PayAction.filter(F.action == "confirm_planned"))
async def cb_confirm_planned(callback: CallbackQuery, callback_data: PayAction, state: FSMContext):
    data = await state.get_data()
    planned = data.get("planned_amount", 0.0)
    await database.mark_payment_paid(callback_data.payment_id, planned)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"✅ Оплата записана: <b>{planned:,.0f}₸</b>", parse_mode="HTML")
    await state.clear()
    await callback.answer()


# ─── Удалить оплату ───────────────────────────────────────────────────────────

@router.callback_query(PayAction.filter(F.action == "delete"))
async def cb_delete_payment(callback: CallbackQuery, callback_data: PayAction):
    await database.delete_payment(callback_data.payment_id)
    await callback.answer("🗑 Удалено", show_alert=False)
    await callback.message.delete()

    payments = await database.get_unpaid_payments(callback.from_user.id)
    if not payments:
        await callback.message.answer("📭 Список оплат пуст.")
    else:
        text, keyboard = _unpaid_keyboard(payments)
        await callback.message.answer(text, reply_markup=keyboard)


# ─── Отчёт ────────────────────────────────────────────────────────────────────

@router.callback_query(PayAction.filter(F.action == "report"))
async def cb_report(callback: CallbackQuery):
    report = await database.get_payments_report(callback.from_user.id)
    now = datetime.now()

    months_ru = ["Январь","Февраль","Март","Апрель","Май","Июнь",
                 "Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"]
    month_label = f"{months_ru[now.month - 1]} {now.year}"

    paid_list    = report["paid"]
    pending_list = report["pending"]
    overdue_list = report["overdue"]

    paid_total    = sum(float(p["paid_amount"])    for p in paid_list)
    pending_total = sum(float(p["planned_amount"]) for p in pending_list)
    overdue_total = sum(float(p["planned_amount"]) for p in overdue_list)

    text = f"📊 <b>Отчёт — {month_label}</b>\n\n"

    if paid_list:
        text += f"✅ Оплачено: {len(paid_list)} шт — <b>{paid_total:,.0f}₸</b>\n"
        for p in paid_list:
            diff = float(p["paid_amount"]) - float(p["planned_amount"])
            diff_str = f" ({'+' if diff >= 0 else ''}{diff:,.0f})" if diff != 0 else ""
            text += f"  • {p['name']}: {float(p['paid_amount']):,.0f}₸{diff_str}\n"
        text += "\n"

    if pending_list:
        text += f"🟡 Ожидают оплаты: {len(pending_list)} шт — <b>{pending_total:,.0f}₸</b>\n"
        for p in pending_list:
            text += f"  • {p['name']} ({p['planned_date'].strftime('%d.%m')}): {float(p['planned_amount']):,.0f}₸\n"
        text += "\n"

    if overdue_list:
        text += f"🔴 Просрочено: {len(overdue_list)} шт — <b>{overdue_total:,.0f}₸</b>\n"
        for p in overdue_list:
            text += f"  • {p['name']} ({p['planned_date'].strftime('%d.%m')}): {float(p['planned_amount']):,.0f}₸\n"
        text += "\n"

    if paid_total or pending_total or overdue_total:
        all_planned = paid_total + pending_total + overdue_total
        text += "━━━━━━━━━━━━━━\n"
        text += f"📋 Итого запланировано: <b>{all_planned:,.0f}₸</b>\n"
        text += f"✅ Оплачено:            <b>{paid_total:,.0f}₸</b>\n"
        remaining = pending_total + overdue_total
        text += f"⏳ Осталось:            <b>{remaining:,.0f}₸</b>"
    else:
        text += "Нет данных за этот месяц."

    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()
