import sqlite3
from datetime import datetime

DB_PATH = "chatbot.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions (id)
        )
    """)
    conn.commit()
    conn.close()


def create_session(name="New chat"):
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO sessions (name, created_at) VALUES (?, ?)",
        (name, datetime.now().isoformat())
    )
    conn.commit()
    session_id = cur.lastrowid
    conn.close()
    return session_id


def get_sessions():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM sessions ORDER BY id DESC").fetchall()
    conn.close()
    return rows


def get_session_messages(session_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC",
        (session_id,)
    ).fetchall()
    conn.close()
    return rows


def save_message(session_id, role, content):
    conn = get_connection()
    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (session_id, role, content, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def rename_session(session_id, new_name):
    conn = get_connection()
    conn.execute("UPDATE sessions SET name = ? WHERE id = ?", (new_name, session_id))
    conn.commit()
    conn.close()


def delete_session(session_id):
    conn = get_connection()
    conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()


def update_session_name_from_first_message(session_id, content):
    """Auto-name a session using the first ~40 chars of the first user message."""
    short_name = content.strip()[:40]
    if len(content.strip()) > 40:
        short_name += "..."
    rename_session(session_id, short_name)