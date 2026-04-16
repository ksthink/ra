import sqlite3
import threading
import time
import logging
from datetime import datetime

from config import DB_PATH, ALARM_MAX_COUNT, ALARM_CHECK_INTERVAL

logger = logging.getLogger(__name__)

_local = threading.local()


def _get_conn():
    if not hasattr(_local, "conn"):
        _local.conn = sqlite3.connect(DB_PATH)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def init_alarm_table():
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS alarms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT NOT NULL,
            playlist_id INTEGER NOT NULL,
            repeat_type TEXT NOT NULL DEFAULT 'daily',
            repeat_days TEXT DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            last_triggered TEXT DEFAULT '',
            FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE
        );
    """)
    conn.commit()


def get_alarms():
    conn = _get_conn()
    rows = conn.execute("""
        SELECT a.id, a.time, a.playlist_id, a.repeat_type, a.repeat_days,
               a.enabled, a.last_triggered, p.name as playlist_name
        FROM alarms a
        LEFT JOIN playlists p ON a.playlist_id = p.id
        ORDER BY a.time
    """).fetchall()
    return [dict(r) for r in rows]


def add_alarm(alarm_time, playlist_id, repeat_type="daily", repeat_days=""):
    conn = _get_conn()
    count = conn.execute("SELECT COUNT(*) FROM alarms").fetchone()[0]
    if count >= ALARM_MAX_COUNT:
        raise ValueError(f"Maximum {ALARM_MAX_COUNT} alarms allowed")

    try:
        datetime.strptime(alarm_time, "%H:%M")
    except ValueError:
        raise ValueError("Invalid time format. Use HH:MM")

    if repeat_type not in ("once", "daily", "weekdays", "weekends", "custom"):
        raise ValueError("Invalid repeat_type")

    conn.execute(
        "INSERT INTO alarms (time, playlist_id, repeat_type, repeat_days, enabled) VALUES (?, ?, ?, ?, 1)",
        (alarm_time, playlist_id, repeat_type, repeat_days),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def update_alarm(alarm_id, **kwargs):
    conn = _get_conn()
    allowed = {"time", "playlist_id", "repeat_type", "repeat_days", "enabled"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return

    if "time" in updates:
        try:
            datetime.strptime(updates["time"], "%H:%M")
        except ValueError:
            raise ValueError("Invalid time format. Use HH:MM")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [alarm_id]
    conn.execute(f"UPDATE alarms SET {set_clause} WHERE id = ?", values)
    conn.commit()


def delete_alarm(alarm_id):
    conn = _get_conn()
    conn.execute("DELETE FROM alarms WHERE id = ?", (alarm_id,))
    conn.commit()


class AlarmScheduler:
    def __init__(self, player):
        self._player = player
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._check_loop, daemon=True)
        self._thread.start()
        logger.info("Alarm scheduler started")

    def stop(self):
        self._running = False

    def _check_loop(self):
        while self._running:
            try:
                self._check_alarms()
            except Exception as e:
                logger.error("Alarm check error: %s", e)
            time.sleep(ALARM_CHECK_INTERVAL)

    def _check_alarms(self):
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_day = now.weekday()
        today_str = now.strftime("%Y-%m-%d")

        # Use fresh connection to see latest alarms added from web UI
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT a.id, a.time, a.playlist_id, a.repeat_type, a.repeat_days,
                   a.enabled, a.last_triggered, p.name as playlist_name
            FROM alarms a
            LEFT JOIN playlists p ON a.playlist_id = p.id
            ORDER BY a.time
        """).fetchall()
        alarms = [dict(r) for r in rows]
        conn.close()

        logger.debug("Alarm check at %s: %d alarms found", current_time, len(alarms))
        for alarm in alarms:
            if not alarm["enabled"]:
                continue
            if alarm["time"] != current_time:
                continue
            if alarm["last_triggered"] == today_str:
                continue
            if self._should_trigger(alarm, current_day):
                self._trigger(alarm, today_str)

    def _should_trigger(self, alarm, current_day):
        repeat_type = alarm["repeat_type"]
        if repeat_type == "daily":
            return True
        elif repeat_type == "once":
            return True
        elif repeat_type == "weekdays":
            return current_day < 5
        elif repeat_type == "weekends":
            return current_day >= 5
        elif repeat_type == "custom":
            days = [int(d) for d in alarm["repeat_days"].split(",") if d.strip().isdigit()]
            return current_day in days
        return False

    def _trigger(self, alarm, today_str):
        logger.info("Triggering alarm %d: playlist %d at %s",
                     alarm["id"], alarm["playlist_id"], alarm["time"])
        try:
            self._player.load_playlist(alarm["playlist_id"])
            conn = sqlite3.connect(DB_PATH)
            conn.execute("UPDATE alarms SET last_triggered = ? WHERE id = ?",
                         (today_str, alarm["id"]))
            if alarm["repeat_type"] == "once":
                conn.execute("UPDATE alarms SET enabled = 0 WHERE id = ?", (alarm["id"],))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Alarm trigger failed: %s", e)
