from aiogram import F
from aiogram.filters import Command

from botlogic.bot import dp, bot, router
from botlogic.start import start_command
from botlogic.home import home_command
from botlogic.callbacks import handle_button_press
from botlogic.checkers import notification_daemon

from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

scheduler.add_job(notification_daemon, "interval", minutes=5)

dp.include_router(router)
dp.message.register(start_command, Command(commands="start"))
dp.message.register(home_command, Command(commands="home"))
dp.callback_query.register(handle_button_press)


async def main():
    scheduler.start()
    scheduler.print_jobs()
    await dp.start_polling(bot)
        

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
