import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


@dataclass
class LogEntry:
    amount_ml: int
    created_at_utc: str


class WaterDB:
    def __init__(self, db_path: str = "water.db"):
        self.db_path = db_path
        self.init_db()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self):
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_goals (
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    daily_goal_ml INTEGER NOT NULL,
                    PRIMARY KEY (chat_id, user_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS water_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    user_label TEXT,
                    amount_ml INTEGER NOT NULL,
                    created_at_utc TEXT NOT NULL
                )
                """
            )

    def set_allowed_chat_id(self, chat_id: int):
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings(key, value) VALUES('allowed_chat_id', ?)",
                (str(chat_id),),
            )

    def get_allowed_chat_id(self):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key='allowed_chat_id'"
            ).fetchone()
            return int(row["value"]) if row else None

    def set_user_goal(self, chat_id: int, user_id: int, goal_ml: int):
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO user_goals(chat_id, user_id, daily_goal_ml)
                VALUES (?, ?, ?)
                """,
                (chat_id, user_id, goal_ml),
            )

    def get_user_goal(self, chat_id: int, user_id: int):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT daily_goal_ml FROM user_goals WHERE chat_id=? AND user_id=?",
                (chat_id, user_id),
            ).fetchone()
            return int(row["daily_goal_ml"]) if row else None

    def add_log(self, chat_id: int, user_id: int, user_label: str, amount_ml: int, created_at_utc: str):
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO water_logs(chat_id, user_id, user_label, amount_ml, created_at_utc)
                VALUES (?, ?, ?, ?, ?)
                """,
                (chat_id, user_id, user_label, amount_ml, created_at_utc),
            )

    def undo_last(self, chat_id: int, user_id: int):
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id, amount_ml FROM water_logs
                WHERE chat_id=? AND user_id=?
                ORDER BY id DESC
                LIMIT 1
                """,
                (chat_id, user_id),
            ).fetchone()
            if not row:
                return None
            conn.execute("DELETE FROM water_logs WHERE id=?", (row["id"],))
            return int(row["amount_ml"])

    def _day_window_utc(self, tz_name: str, for_date=None):
        tz = ZoneInfo(tz_name)
        now_local = datetime.now(tz)
        target = for_date or now_local.date()
        start_local = datetime(target.year, target.month, target.day, tzinfo=tz)
        end_local = start_local + timedelta(days=1)
        return start_local.astimezone(ZoneInfo("UTC")), end_local.astimezone(ZoneInfo("UTC"))

    def get_today_user_total(self, chat_id: int, user_id: int, tz_name: str):
        start_utc, end_utc = self._day_window_utc(tz_name)
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(amount_ml), 0) AS total
                FROM water_logs
                WHERE chat_id=? AND user_id=?
                  AND created_at_utc>=? AND created_at_utc<?
                """,
                (chat_id, user_id, start_utc.isoformat(), end_utc.isoformat()),
            ).fetchone()
            return int(row["total"])

    def get_today_timeline(self, chat_id: int, user_id: int, tz_name: str):
        start_utc, end_utc = self._day_window_utc(tz_name)
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT amount_ml, created_at_utc
                FROM water_logs
                WHERE chat_id=? AND user_id=?
                  AND created_at_utc>=? AND created_at_utc<?
                ORDER BY id ASC
                """,
                (chat_id, user_id, start_utc.isoformat(), end_utc.isoformat()),
            ).fetchall()
            return [LogEntry(int(r["amount_ml"]), r["created_at_utc"]) for r in rows]

    def get_today_group_leaderboard(self, chat_id: int, tz_name: str, limit: int = 20):
        start_utc, end_utc = self._day_window_utc(tz_name)
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT user_id, COALESCE(MAX(user_label), CAST(user_id AS TEXT)) AS user_label,
                       SUM(amount_ml) AS total
                FROM water_logs
                WHERE chat_id=? AND created_at_utc>=? AND created_at_utc<?
                GROUP BY user_id
                ORDER BY total DESC, user_id ASC
                LIMIT ?
                """,
                (chat_id, start_utc.isoformat(), end_utc.isoformat(), limit),
            ).fetchall()
            return [(int(r["user_id"]), r["user_label"], int(r["total"])) for r in rows]

    def get_daily_series(self, chat_id: int, user_id: int, tz_name: str, days: int = 7):
        tz = ZoneInfo(tz_name)
        today = datetime.now(tz).date()
        series = []
        with self.connect() as conn:
            for i in range(days - 1, -1, -1):
                day = today - timedelta(days=i)
                start_local = datetime(day.year, day.month, day.day, tzinfo=tz)
                end_local = start_local + timedelta(days=1)
                row = conn.execute(
                    """
                    SELECT COALESCE(SUM(amount_ml), 0) AS total
                    FROM water_logs
                    WHERE chat_id=? AND user_id=?
                      AND created_at_utc>=? AND created_at_utc<?
                    """,
                    (
                        chat_id,
                        user_id,
                        start_local.astimezone(ZoneInfo("UTC")).isoformat(),
                        end_local.astimezone(ZoneInfo("UTC")).isoformat(),
                    ),
                ).fetchone()
                series.append((day.isoformat(), int(row["total"])))
        return series
