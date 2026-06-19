from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters.callback_data import CallbackData
from aiogram_calendar import SimpleCalendar
from datetime import datetime, date as date_type
import calendar as cal_module

import database


def _next_monthly_date(day: int) -> date_type:
    today = date_type.today()
    month = today.month % 12 + 1
    year  = today.year + (1 if today.month == 12 else 0)
    max_d = cal_module.monthrange(year, month)[1]
    return date_type(year, month, min(day, max_d))


async def _maybe_rollover(user_id: int, payment):
    """Если платёж ежемесячный — создаёт запись на следующий месяц."""
    day = payment["day_of_month"]
    if not day:
        return
    next_date = _next_monthly_date(day)
    await database.add_payment(
        user_id=user_id,
        name=payment["name"],
        category=payment["category"] or "other",
        planned_amount=float(payment["planned_amount"]),
        planned_date=next_date,
        day_of_month=day,
    )

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
    waiting_for_name   = State()
    waiting_for_amount = State()
    waiting_for_date   = State()   # calendar — обрабатывается в Bot_TG.py


class PaymentPayState(StatesGroup):
    waiting_for_paid_amount = State()


class ExpenseAddState(StatesGroup):
    waiting_for_description = State()
    waiting_for_amount      = State()


# ─── Callback Data ────────────────────────────────────────────────────────────

class PayAction(CallbackData, prefix="payact"):
    action:     str
    payment_id: int = 0


# ─── Вспомогательные функции ──────────────────────────────────────────────────

def _unpaid_keyboard(payments) -> tuple[str, InlineKeyboardMarkup]:
    today = datetime.now().date()
    text = "💳 Запланированные оплаты:\n\n"
    buttons = []
    for p in payments:
        d = p["planned_date"]
        status = "🔴" if d < today else ("🟡" if d == today else "🟢")
        cat = CATEGORIES.get(p["category"], "📦 Другое")
        day_label = f" (каждого {p['day_of_month']}-го)" if p.get("day_of_month") else ""
        text += f"{status} {d.strftime('%d.%m.%Y')} | {cat} | {p['name']}{day_label}: {p['planned_amount']:,.0f}₸\n"
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
            InlineKeyboardButton(text="💸 Затраты",        callback_data=PayAction(action="expense").pack()),
            InlineKeyboardButton(text="📊 Отчёт за месяц", callback_data=PayAction(action="report").pack()),
        ],
    ])
    await message.answer("💳 Планировщик оплат:", reply_markup=kb)


# ─── Добавить ежемесячный платёж ──────────────────────────────────────────────

@router.callback_query(PayAction.filter(F.action == "add"))
async def cb_add_payment(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PaymentAddState.waiting_for_name)
    await callback.message.answer(
        "📝 Введи название ежемесячного платежа:\n"
        "<i>например: Аренда, Кредит, Netflix, Коммуналка</i>\n\n"
        "❌ Нажми «Отмена» чтобы выйти.",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(PaymentAddState.waiting_for_name)
async def got_payment_name(message: Message, state: FSMContext):
    await state.update_data(payment_name=message.text.strip())
    await state.set_state(PaymentAddState.waiting_for_amount)
    await message.answer("💰 Введи сумму платежа в тенге:")


@router.message(PaymentAddState.waiting_for_amount)
async def got_payment_amount(message: Message, state: FSMContext):
    raw = message.text.strip().replace(",", ".").replace(" ", "").replace(" ", "")
    try:
        amount = float(raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи сумму числом, например: <b>15000</b>", parse_mode="HTML")
        return

    await state.update_data(payment_amount=amount)
    await state.set_state(PaymentAddState.waiting_for_date)
    await message.answer(
        "📅 Выбери число месяца для ежемесячной оплаты:",
        reply_markup=await SimpleCalendar().start_calendar()
    )


# waiting_for_date обрабатывается в Bot_TG.py (общий calendar handler)


# ─── Затраты ──────────────────────────────────────────────────────────────────

@router.callback_query(PayAction.filter(F.action == "expense"))
async def cb_expense_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ExpenseAddState.waiting_for_description)
    await callback.message.answer("📝 На что потратил? Введи описание:\n\n❌ Нажми «Отмена» чтобы выйти.")
    await callback.answer()


@router.message(ExpenseAddState.waiting_for_description)
async def got_expense_description(message: Message, state: FSMContext):
    await state.update_data(expense_description=message.text.strip())
    await state.set_state(ExpenseAddState.waiting_for_amount)
    await message.answer("💰 Введи сумму в тенге:")


@router.message(ExpenseAddState.waiting_for_amount)
async def got_expense_amount(message: Message, state: FSMContext):
    raw = message.text.strip().replace(",", ".").replace(" ", "").replace(" ", "")
    try:
        amount = float(raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи сумму числом, например: <b>5000</b>", parse_mode="HTML")
        return

    data = await state.get_data()
    await database.add_expense(
        user_id=message.from_user.id,
        description=data["expense_description"],
        amount=amount,
    )
    await message.answer(
        f"✅ Затрата записана!\n\n"
        f"📌 {data['expense_description']}\n"
        f"💸 {amount:,.0f}₸",
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
    raw = message.text.strip().replace(",", ".").replace(" ", "").replace(" ", "")
    try:
        amount = float(raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи сумму числом, например: <b>15000</b>", parse_mode="HTML")
        return

    data = await state.get_data()
    payment = await database.get_payment_by_id(data["paying_id"])
    await database.mark_payment_paid(data["paying_id"], amount)
    await _maybe_rollover(message.from_user.id, payment)

    diff = amount - data["planned_amount"]
    diff_str = f"  ({'+' if diff >= 0 else ''}{diff:,.0f}₸ от плана)" if diff != 0 else ""
    rollover_str = (
        f"\n🔄 Следующий платёж перенесён на "
        f"{_next_monthly_date(payment['day_of_month']).strftime('%d.%m.%Y')}"
        if payment["day_of_month"] else ""
    )
    await message.answer(
        f"✅ Оплата записана: <b>{amount:,.0f}₸</b>{diff_str}{rollover_str}",
        parse_mode="HTML"
    )
    await state.clear()


@router.callback_query(PayAction.filter(F.action == "confirm_planned"))
async def cb_confirm_planned(callback: CallbackQuery, callback_data: PayAction, state: FSMContext):
    data = await state.get_data()
    planned = data.get("planned_amount", 0.0)
    payment = await database.get_payment_by_id(callback_data.payment_id)
    await database.mark_payment_paid(callback_data.payment_id, planned)
    await _maybe_rollover(callback.from_user.id, payment)

    rollover_str = (
        f"\n🔄 Следующий платёж перенесён на "
        f"{_next_monthly_date(payment['day_of_month']).strftime('%d.%m.%Y')}"
        if payment["day_of_month"] else ""
    )
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✅ Оплата записана: <b>{planned:,.0f}₸</b>{rollover_str}",
        parse_mode="HTML"
    )
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
    report   = await database.get_payments_report(callback.from_user.id)
    expenses = await database.get_expenses_report(callback.from_user.id)
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
    expense_total = sum(float(e["amount"])         for e in expenses)

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

    if expenses:
        text += f"💸 Затраты: {len(expenses)} шт — <b>{expense_total:,.0f}₸</b>\n"
        for e in expenses:
            day = e["created_at"].strftime("%d.%m")
            text += f"  • {day} {e['description']}: {float(e['amount']):,.0f}₸\n"
        text += "\n"

    has_data = paid_total or pending_total or overdue_total or expense_total
    if has_data:
        all_planned = paid_total + pending_total + overdue_total
        text += "━━━━━━━━━━━━━━\n"
        text += f"📋 Запланировано:  <b>{all_planned:,.0f}₸</b>\n"
        text += f"✅ Оплачено:       <b>{paid_total:,.0f}₸</b>\n"
        remaining = pending_total + overdue_total
        text += f"⏳ Осталось:       <b>{remaining:,.0f}₸</b>\n"
        text += f"💸 Доп. затраты:   <b>{expense_total:,.0f}₸</b>\n"
        text += f"📉 Всего потрачено: <b>{paid_total + expense_total:,.0f}₸</b>"
    else:
        text += "Нет данных за этот месяц."

    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()
