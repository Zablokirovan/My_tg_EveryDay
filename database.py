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
        await conn.execute(
            """
            INSERT INTO tg_bot_strih.user_info (id_user, user_name, first_name)
            VALUES ($1, $2, $3)
            """,
            data[0], data[1], data[2]
        )


async def writing_note_user(data):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO tg_bot_strih.writing_note_user (user_id, date_create, text, date_complete)
            VALUES ($1, $2, $3, $4)
            """,
            data[0], data[1], data[2], data[3]
        )
