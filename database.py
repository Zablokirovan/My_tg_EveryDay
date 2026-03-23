import os
from dotenv import load_dotenv
import asyncpg

load_dotenv()

pool = None

async def create_pool():
    global pool
    pool = await asyncpg.create_pool(
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT"))
    )


async def get_data():
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM tg_bot_strih.user_info")
        return rows

async def record_data_user(data: list):
    async with pool.acquire() as conn:
        rows = await conn.fetch("INSERT INTO tg_bot_strih.user_info"
                                "VALUES (s%, s%, s%)",data)
        return rows
