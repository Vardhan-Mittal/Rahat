"""Persistence for people who opted in, SOS requests, zone alerts and their replies.

SQLite keeps the hackathon setup to one file; every row is written by a real user or operator action.
"""

import asyncio
import json
import os
import sqlite3
import threading
import time
from pathlib import Path

from .geo import km

DB_PATH = Path(os.getenv("RAHAT_DB", Path(__file__).resolve().parent.parent / "data" / "rahat.db"))
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  chat_id INTEGER PRIMARY KEY,
  name TEXT,
  lang TEXT DEFAULT 'hi',
  lat REAL, lon REAL,
  consent INTEGER DEFAULT 0,
  updated REAL
);
CREATE TABLE IF NOT EXISTS sos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id INTEGER, channel TEXT, text TEXT, lat REAL, lon REAL,
  need TEXT, level TEXT, shelter TEXT, created REAL
);
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  place TEXT, level TEXT, lat REAL, lon REAL, radius_km REAL,
  text_hi TEXT, text_en TEXT, shelter TEXT, created REAL
);
CREATE TABLE IF NOT EXISTS deliveries (
  alert_id INTEGER, chat_id INTEGER,
  status TEXT,            -- sent | heard | safe | help | failed
  attempts INTEGER DEFAULT 1,
  updated REAL,
  PRIMARY KEY (alert_id, chat_id)
);
"""


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
    return _conn


def _run(fn, *args):
    def locked():
        with _lock:
            out = fn(_db(), *args)
            _db().commit()
            return out
    return asyncio.to_thread(locked)


# ---------- users

async def upsert_user(chat_id: int, name: str | None = None, lang: str | None = None,
                      lat: float | None = None, lon: float | None = None, consent: bool | None = None) -> None:
    def q(c: sqlite3.Connection):
        c.execute("INSERT OR IGNORE INTO users (chat_id, updated) VALUES (?, ?)", (chat_id, time.time()))
        for col, val in (("name", name), ("lang", lang), ("lat", lat), ("lon", lon),
                         ("consent", None if consent is None else int(consent))):
            if val is not None:
                c.execute(f"UPDATE users SET {col} = ?, updated = ? WHERE chat_id = ?", (val, time.time(), chat_id))
    await _run(q)


async def get_user(chat_id: int) -> dict | None:
    def q(c: sqlite3.Connection):
        r = c.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
        return dict(r) if r else None
    return await _run(q)


async def users_within(lat: float, lon: float, radius_km: float) -> list[dict]:
    def q(c: sqlite3.Connection):
        rows = c.execute("SELECT * FROM users WHERE consent = 1 AND lat IS NOT NULL").fetchall()
        return [dict(r) for r in rows if km(lat, lon, r["lat"], r["lon"]) <= radius_km]
    return await _run(q)


# ---------- SOS log

async def log_sos(chat_id: int | None, channel: str, text: str, lat: float | None, lon: float | None,
                  need: str | None, level: str | None, shelter: str | None) -> None:
    await _run(lambda c: c.execute(
        "INSERT INTO sos (chat_id, channel, text, lat, lon, need, level, shelter, created) VALUES (?,?,?,?,?,?,?,?,?)",
        (chat_id, channel, text, lat, lon, need, level, shelter, time.time())))


async def recent_sos(limit: int = 20) -> list[dict]:
    def q(c: sqlite3.Connection):
        return [dict(r) for r in c.execute("SELECT * FROM sos ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]
    return await _run(q)


# ---------- zone alerts and replies

async def create_alert(place: str, level: str, lat: float, lon: float, radius_km: float,
                       text_hi: str, text_en: str, shelter: dict | None) -> int:
    def q(c: sqlite3.Connection):
        cur = c.execute(
            "INSERT INTO alerts (place, level, lat, lon, radius_km, text_hi, text_en, shelter, created) VALUES (?,?,?,?,?,?,?,?,?)",
            (place, level, lat, lon, radius_km, text_hi, text_en, json.dumps(shelter) if shelter else None, time.time()))
        return cur.lastrowid
    return await _run(q)


async def get_alert(alert_id: int) -> dict | None:
    def q(c: sqlite3.Connection):
        r = c.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["shelter"] = json.loads(d["shelter"]) if d["shelter"] else None
        return d
    return await _run(q)


async def set_delivery(alert_id: int, chat_id: int, status: str) -> None:
    order = {"failed": -1, "sent": 0, "heard": 1, "safe": 2, "help": 2}

    def q(c: sqlite3.Connection):
        r = c.execute("SELECT status FROM deliveries WHERE alert_id = ? AND chat_id = ?", (alert_id, chat_id)).fetchone()
        if r is None:
            c.execute("INSERT INTO deliveries (alert_id, chat_id, status, updated) VALUES (?,?,?,?)",
                      (alert_id, chat_id, status, time.time()))
        elif order.get(status, 0) >= order.get(r["status"], 0) or status == "help":
            # never move someone backwards (safe -> heard), but "help" always wins
            c.execute("UPDATE deliveries SET status = ?, updated = ? WHERE alert_id = ? AND chat_id = ?",
                      (status, time.time(), alert_id, chat_id))
    await _run(q)


async def bump_attempt(alert_id: int, chat_id: int) -> None:
    await _run(lambda c: c.execute(
        "UPDATE deliveries SET attempts = attempts + 1, updated = ? WHERE alert_id = ? AND chat_id = ?",
        (time.time(), alert_id, chat_id)))


async def unheard(older_than_s: float, max_attempts: int) -> list[dict]:
    def q(c: sqlite3.Connection):
        rows = c.execute(
            "SELECT * FROM deliveries WHERE status = 'sent' AND updated < ? AND attempts < ?",
            (time.time() - older_than_s, max_attempts)).fetchall()
        return [dict(r) for r in rows]
    return await _run(q)


async def funnel(alert_id: int | None = None) -> dict:
    """Counts for one alert (or the latest one). Everyone who heard includes those who later replied."""
    def q(c: sqlite3.Connection):
        a = (c.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone() if alert_id
             else c.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT 1").fetchone())
        if not a:
            return {"alert": None, "alerted": 0, "heard": 0, "safe": 0, "help": 0, "failed": 0}
        rows = c.execute("SELECT status, COUNT(*) n FROM deliveries WHERE alert_id = ? GROUP BY status", (a["id"],)).fetchall()
        n = {r["status"]: r["n"] for r in rows}
        sent_ok = sum(v for k, v in n.items() if k != "failed")
        return {
            "alert": {"id": a["id"], "place": a["place"], "level": a["level"], "created": a["created"]},
            "alerted": sent_ok,
            "heard": n.get("heard", 0) + n.get("safe", 0) + n.get("help", 0),
            "safe": n.get("safe", 0),
            "help": n.get("help", 0),
            "failed": n.get("failed", 0),
        }
    return await _run(q)
