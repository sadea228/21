from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_join_keyboard() -> InlineKeyboardMarkup:
    """Создаёт инлайн-клавиатуру с кнопкой присоединения к игре."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🎮 Присоединиться к игре", callback_data="join_game")
    return builder.as_markup()

def get_game_actions_keyboard() -> InlineKeyboardMarkup:
    """Создаёт инлайн-клавиатуру с кнопками игровых действий."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🃏 Взять карту", callback_data="hit")
    builder.button(text="🛑 Остановиться", callback_data="stand")
    builder.adjust(2)  # Располагаем кнопки в один ряд
    return builder.as_markup() 