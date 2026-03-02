from aiogram import Bot, Dispatcher, Router, F
from aiogram.fsm.storage.memory import MemoryStorage
from lib.controldb import DBControl
import logging
import os

API_TOKEN = '8583625924:AAF5KKysxqPyzXmVtnJ0CqqF0Y8DfEHBr1Y'

def get_clickhouse_dsn() -> str:
    """Получение DSN строки для ClickHouse из переменных окружения или напрямую"""
    # Вариант 1: Из переменных окружения
    host = os.getenv('CLICKHOUSE_HOST', 'uebki-db')
    port = os.getenv('CLICKHOUSE_PORT', '4532')
    username = os.getenv('CLICKHOUSE_USER', 'default')
    password = os.getenv('CLICKHOUSE_PASSWORD', '')
    database = os.getenv('CLICKHOUSE_DATABASE', 'uebki39bot')
    
    # Форматируем DSN
    if password:
        dsn = f"clickhouse://{username}:{password}@{host}:{port}/{database}"
    else:
        dsn = f"clickhouse://{username}@{host}:{port}/{database}"
    
    return dsn

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
router = Router()
db = DBControl(db_uri=get_clickhouse_dsn())

dp = Dispatcher(storage=storage)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)