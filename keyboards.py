from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import database

button = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🌤 Сводка на день")],
    [KeyboardButton(text="Календарь"),  KeyboardButton(text="Мои задачи")],
    [KeyboardButton(text="💳 Оплаты")],
], resize_keyboard=True)

button_female = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🌤 Сводка на день")],
    [KeyboardButton(text="Календарь"),  KeyboardButton(text="Мои задачи")],
    [KeyboardButton(text="💳 Оплаты"), KeyboardButton(text="🌸 Цикл")],
], resize_keyboard=True)

cancel_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True
)


async def get_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    user = await database.get_user(user_id)
    if user and user["gender"] == "female":
        return button_female
    return button
