import os
from datetime import date
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
    await _migrate()


async def _migrate():
    async with pool.acquire() as conn:
        # Добавить id в таблицу заметок если нет
        await conn.execute("""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'tg_bot_strih'
                      AND table_name   = 'writing_note_user'
                      AND column_name  = 'id'
                ) THEN
                    ALTER TABLE tg_bot_strih.writing_note_user
                        ADD COLUMN id SERIAL PRIMARY KEY;
                END IF;
            END $$;
        """)
        # Таблица оплат
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tg_bot_strih.payments (
                id             SERIAL PRIMARY KEY,
                user_id        BIGINT         NOT NULL,
                name           VARCHAR(255)   NOT NULL,
                category       VARCHAR(50)    DEFAULT 'other',
                planned_amount DECIMAL(12, 2) NOT NULL,
                planned_date   DATE           NOT NULL,
                paid_date      DATE,
                paid_amount    DECIMAL(12, 2),
                created_at     TIMESTAMP      DEFAULT NOW()
            )
        """)


# ─── Пользователи ────────────────────────────────────────────────────────────

async def record_data_user(data: list):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO tg_bot_strih.user_info (id_user, user_name, first_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (id_user) DO NOTHING
            """,
            data[0], data[1], data[2]
        )


# ─── Заметки / задачи ────────────────────────────────────────────────────────

async def writing_note_user(data: list):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO tg_bot_strih.writing_note_user (user_id, date_create, text, date_complete)
            VALUES ($1, $2, $3, $4)
            """,
            data[0], data[1], data[2], data[3]
        )


async def get_user_notes(user_id: int):
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT id, text, date_complete
            FROM tg_bot_strih.writing_note_user
            WHERE user_id = $1
            ORDER BY date_complete ASC
            """,
            user_id
        )


async def get_notes_due_today():
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT user_id, text
            FROM tg_bot_strih.writing_note_user
            WHERE date_complete = CURRENT_DATE
            ORDER BY user_id
            """
        )


async def delete_user_note(note_id: int):
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM tg_bot_strih.writing_note_user WHERE id = $1",
            note_id
        )


# ─── Оплаты ──────────────────────────────────────────────────────────────────

async def add_payment(user_id: int, name: str, category: str,
                      planned_amount: float, planned_date):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO tg_bot_strih.payments
                (user_id, name, category, planned_amount, planned_date)
            VALUES ($1, $2, $3, $4, $5)
            """,
            user_id, name, category, planned_amount, planned_date
        )


async def get_unpaid_payments(user_id: int):
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT id, name, category, planned_amount, planned_date
            FROM tg_bot_strih.payments
            WHERE user_id = $1 AND paid_date IS NULL
            ORDER BY planned_date ASC
            """,
            user_id
        )


async def get_payment_by_id(payment_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT id, name, planned_amount, planned_date
            FROM tg_bot_strih.payments
            WHERE id = $1
            """,
            payment_id
        )


async def mark_payment_paid(payment_id: int, paid_amount: float):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE tg_bot_strih.payments
            SET paid_date = CURRENT_DATE, paid_amount = $2
            WHERE id = $1
            """,
            payment_id, paid_amount
        )


async def delete_payment(payment_id: int):
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM tg_bot_strih.payments WHERE id = $1",
            payment_id
        )


async def get_payments_report(user_id: int) -> dict:
    today = date.today()
    first_day = today.replace(day=1)
    async with pool.acquire() as conn:
        paid = await conn.fetch(
            """
            SELECT name, planned_amount, paid_amount, paid_date
            FROM tg_bot_strih.payments
            WHERE user_id = $1
              AND paid_date >= $2
            ORDER BY paid_date
            """,
            user_id, first_day
        )
        pending = await conn.fetch(
            """
            SELECT id, name, category, planned_amount, planned_date
            FROM tg_bot_strih.payments
            WHERE user_id = $1
              AND paid_date IS NULL
              AND planned_date >= $2
            ORDER BY planned_date
            """,
            user_id, today
        )
        overdue = await conn.fetch(
            """
            SELECT id, name, category, planned_amount, planned_date
            FROM tg_bot_strih.payments
            WHERE user_id = $1
              AND paid_date IS NULL
              AND planned_date < $2
            ORDER BY planned_date
            """,
            user_id, today
        )
    return {"paid": paid, "pending": pending, "overdue": overdue}
