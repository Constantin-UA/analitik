import aiosqlite
import logging
import datetime
from typing import List, Dict, Optional

DB_FILE = "trading_journal.db"

async def init_db() -> None:
    """
    Ініціалізація схеми БД.
    Чому IF NOT EXISTS: забезпечує імутабельність і безпечний повторний запуск контейнера 
    без ризику затирання існуючої історії угод.
    """
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    volume REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    pnl_usd REAL DEFAULT 0.0,
                    open_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    close_time TIMESTAMP
                )
            """)
            await db.commit()
    except Exception:
        logging.exception("Критична помилка ініціалізації бази даних SQLite")

async def open_trade(symbol: str, side: str, entry_price: float, sl: float, tp: float, volume: float) -> None:
    """Фіксує нову угоду в системі. Бот починає автономне стеження за нею."""
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "INSERT INTO trades (symbol, side, entry_price, stop_loss, take_profit, volume, status) VALUES (?, ?, ?, ?, ?, ?, 'OPEN')",
                (symbol, side, entry_price, sl, tp, volume)
            )
            await db.commit()
    except Exception:
        logging.exception(f"Збій запису нової угоди {side} по {symbol}")

async def get_open_trades() -> List[Dict]:
    """Витягує всі активні угоди для перевірки в циклі check_alerts."""
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM trades WHERE status = 'OPEN'") as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    except Exception:
        logging.exception("Помилка читання відкритих угод з БД")
        return []

async def close_trade(trade_id: int, close_price: float, pnl_usd: float, result_type: str) -> None:
    """
    Термінація життєвого циклу угоди.
    Чому result_type: дозволяє розрізняти закриття по TP, SL або ручне скасування.
    """
    close_time = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "UPDATE trades SET status = ?, pnl_usd = ?, close_time = ? WHERE id = ?",
                (result_type, pnl_usd, close_time, trade_id)
            )
            await db.commit()
    except Exception:
        logging.exception(f"Збій закриття угоди ID {trade_id}")