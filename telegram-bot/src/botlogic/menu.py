from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import Message
from aiogram.enums import ParseMode
from botlogic.bot import db

async def main_menu(message: Message, user_id: int):
    user = db.get_user_by_telegram_id(user_id)
    balance = user.balance or 0
    published = bool(user.published)
    
    act = "✅ <b>Активна</b>" if published else "❌ <b>Скрыта</b>"

    intro = (
        f"👋 Привет, <b>{user.name}</b>!\n\n"
        f"👭 Пригласи друзей и получи <b>10 🌻</b> за каждого!\n"
        f"🌻 Подсолнухи бесплатны и нужны чтобы тэгать людей 🌻\n\n"
        f"💰 <b>Ваш баланс:</b> {balance} 🌻\n"
        f"📝 <b>Анкета:</b> {act}"
    )

    builder = InlineKeyboardBuilder()

    # Строка 1: Моя анкета
    builder.row(
        InlineKeyboardButton(text="🖼 Моя анкета", callback_data="my_profile")
    )
    #builder.row(
    #    InlineKeyboardButton(text="👾 Добавить анкету", callback_data="add_user")
    #)

    # Строка 2: Начать оценку, Топ юзеров
    builder.row(
        InlineKeyboardButton(text="🔥 Начать оценку", callback_data="start_rating"),
        InlineKeyboardButton(text="🏆 Топ юзеров", callback_data="top_users")
    )

    # Строка 3: Мои теги / чужие теги
    builder.row(
        InlineKeyboardButton(text="🏷 Мои теги", callback_data="my_tags"),
        InlineKeyboardButton(text="➕ Добавить тег", callback_data="create_tag")
    )

    # Строка 4: Пригласить друга
    builder.row(
        InlineKeyboardButton(text="📡 Пригласить 🚀", callback_data="invite")
    )

    # Строка 5: Поддержка
    builder.row(
        InlineKeyboardButton(text="👨‍💻 Поддержка", url="https://t.me/uebki_supportbot")
    )

    keyboard = builder.as_markup()

    await message.answer(
        intro,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )

    return 0
