from botlogic.menu import main_menu
from botlogic.bot import db
from aiogram import types

async def home_command(message: types.Message):
    user_id = message.from_user.id
    user = db.get_user_by_telegram_id(user_id)
    
    if not user:
        await message.answer("Пожалуйста, используйте команду /start для регистрации. \n Please use /start command for registration")
        return
    elif user.banned == True:
        await message.answer("Вы забанены. Обратитесь к администратору")
        return
    
    await main_menu(message, user_id)