import sqlite3
import threading
import subprocess
import json
import logging

from config import DB_PATH

logger = logging.getLogger(__name__)

_local = threading.local()


def _get_conn():
    if not hasattr(_local, "conn"):
        _local.conn = sqlite3.connect(DB_PATH)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def init_db():
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            yt_url TEXT NOT NULL,
            yt_id TEXT NOT NULL UNIQUE,
            thumbnail_url TEXT,
            track_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            playlist_id INTEGER NOT NULL,
            video_id TEXT NOT NULL,
            title TEXT NOT NULL,
            thumbnail_url TEXT,
            duration INTEGER DEFAULT 0,
            position INTEGER NOT NULL,
            FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        INSERT OR IGNORE INTO settings (key, value) VALUES ('screensaver_timeout', '10');
        INSERT OR IGNORE INTO settings (key, value) VALUES ('screensaver_enabled', '1');
        INSERT OR IGNORE INTO settings (key, value) VALUES ('volume', '70');
    """)
    conn.commit()


def _extract_playlist_id(url):
    if "list=" in url:
        for part in url.split("list=")[1].split("&"):
            return part
    return url.strip()


def fetch_playlist_info(url):
    yt_id = _extract_playlist_id(url)
    full_url = f"https://www.youtube.com/playlist?list={yt_id}"
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-json",
        "--no-warnings",
        "--quiet",
        full_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr[:300]}")

    tracks = []
    playlist_title = None
    playlist_thumb = None
    for i, line in enumerate(result.stdout.strip().split("\n")):
        if not line:
            continue
        entry = json.loads(line)
        if playlist_title is None:
            playlist_title = entry.get("playlist_title", f"Playlist {yt_id}")
            playlist_thumb = entry.get("playlist_thumbnails", [{}])[0].get("url") if entry.get("playlist_thumbnails") else None
        tracks.append({
            "video_id": entry.get("id", ""),
            "title": entry.get("title", "Unknown"),
            "thumbnail_url": entry.get("thumbnails", [{}])[-1].get("url", "") if entry.get("thumbnails") else "",
            "duration": int(entry.get("duration") or 0),
            "position": i,
        })

    return {
        "name": playlist_title or f"Playlist {yt_id}",
        "yt_url": full_url,
        "yt_id": yt_id,
        "thumbnail_url": playlist_thumb or (tracks[0]["thumbnail_url"] if tracks else ""),
        "tracks": tracks,
    }


def add_playlist(url):
    info = fetch_playlist_info(url)
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO playlists (name, yt_url, yt_id, thumbnail_url, track_count) VALUES (?, ?, ?, ?, ?)",
            (info["name"], info["yt_url"], info["yt_id"], info["thumbnail_url"], len(info["tracks"])),
        )
        playlist_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        for t in info["tracks"]:
            conn.execute(
                "INSERT INTO tracks (playlist_id, video_id, title, thumbnail_url, duration, position) VALUES (?, ?, ?, ?, ?, ?)",
                (playlist_id, t["video_id"], t["title"], t["thumbnail_url"], t["duration"], t["position"]),
            )
        conn.commit()
        return {"id": playlist_id, **info, "track_count": len(info["tracks"])}
    except sqlite3.IntegrityError:
        conn.rollback()
        raise ValueError(f"Playlist '{info['yt_id']}' already exists")


def get_playlists():
    conn = _get_conn()
    rows = conn.execute("SELECT id, name, yt_url, yt_id, thumbnail_url, track_count FROM playlists ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def get_tracks(playlist_id):
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, video_id, title, thumbnail_url, duration, position FROM tracks WHERE playlist_id = ? ORDER BY position",
        (playlist_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_playlist(playlist_id):
    conn = _get_conn()
    row = conn.execute("SELECT id, name, yt_url, yt_id, thumbnail_url, track_count FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
    if row is None:
        return None
    return dict(row)


def delete_playlist(playlist_id):
    conn = _get_conn()
    conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
    conn.commit()


def get_setting(key, default=None):
    conn = _get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    conn = _get_conn()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()


def get_all_settings():
    conn = _get_conn()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}
