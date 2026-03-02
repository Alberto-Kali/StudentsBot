from aiogram.utils.deep_linking import decode_payload
from aiogram import types
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.state import State, StatesGroup
import asyncio


from botlogic.callbacks import Form
from botlogic.bot import bot, db
from botlogic.menu import main_menu


async def start_command(message: types.Message):
    telegram_id = message.from_user.id
    telegram_uname = message.from_user.username or None
    full_name = message.from_user.full_name

    # Проверка: пользователь существует?
    user = db.get_user_by_telegram_id(telegram_id)

    if user:
        hi_text = f"🔐 Рады видеть вас снова {telegram_uname or telegram_id}!"
    else:
        # Создание пользователя
        user = db.create_user(
            name=full_name,
            telegram_uname=telegram_uname,
            telegram_id=telegram_id,
            biography=""
        )
        
        hi_text = f"🔐 Добро пожаловать, {telegram_uname or telegram_id}!"

        # Проверка на реферальную ссылку
        refer_parts = message.text.split(" ")
        if len(refer_parts) > 1:
            try:
                refer_id = int(decode_payload(refer_parts[1]))
                ref_user = db.get_user_by_telegram_id(refer_id)
                if ref_user and ref_user.telegram_id != telegram_id:
                    # Начисляем бонус
                    new_balance = ref_user.balance + 10
                    db.edit_user(refer_id, balance=new_balance)

                    # Уведомляем пригласившего
                    builder = InlineKeyboardBuilder()
                    builder.row(
                        InlineKeyboardButton(
                            text="❌ Закрыть ✅", 
                            callback_data="close"
                        )
                    )

                    await bot.send_message(
                        chat_id=refer_id,
                        text="📨 По вашей ссылке перешёл пользователь!\n🌻 На ваш баланс начислено 10 подсолнухов!",
                        reply_markup=builder.as_markup()
                    )
            except Exception as e:
                print(f"[Ошибка при обработке реферала]: {e}")

    # Отправляем приветствие
    hi_msg = await message.answer(hi_text)

    # Удаляем сообщение через 2 секунды
    await asyncio.sleep(2)
    try:
        await bot.delete_message(chat_id=telegram_id, message_id=hi_msg.message_id)
    except:
        pass  # если бот не может удалить сообщение — просто игнорируем

    # Переход в главное меню
    await main_menu(message, telegram_id)

    return 0
