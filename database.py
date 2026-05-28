import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", "data.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS instagram_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            instagram_id TEXT,
            username TEXT,
            access_token TEXT,
            token_expires_at TEXT
        );

        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            keyword TEXT NOT NULL,
            message TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            text TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            stripe_session_id TEXT,
            starts_at TEXT DEFAULT (datetime('now')),
            expires_at TEXT,
            active INTEGER DEFAULT 1
        );
    """)
    conn.commit()
    conn.close()


# --- Users ---

def create_user(email: str, password_hash: str) -> int:
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO users (email, password_hash) VALUES (?, ?)",
        (email, password_hash),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return user_id


def get_user_by_email(email: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return row


def get_user_by_id(user_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return row


def get_user_by_instagram_id(instagram_id: str):
    conn = get_db()
    row = conn.execute("""
        SELECT u.* FROM users u
        JOIN instagram_accounts ia ON ia.user_id = u.id
        WHERE ia.instagram_id = ?
    """, (instagram_id,)).fetchone()
    conn.close()
    return row


# --- Instagram Accounts ---

def create_instagram_account(user_id: int, instagram_id: str, username: str, access_token: str) -> int:
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO instagram_accounts (user_id, instagram_id, username, access_token) VALUES (?, ?, ?, ?)",
        (user_id, instagram_id, username, access_token),
    )
    conn.commit()
    account_id = cur.lastrowid
    conn.close()
    return account_id


def get_instagram_account(user_id: int):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM instagram_accounts WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return row


def delete_instagram_account(user_id: int):
    conn = get_db()
    conn.execute("DELETE FROM instagram_accounts WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_instagram_account_by_ig_id(instagram_id: str):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM instagram_accounts WHERE instagram_id = ?", (instagram_id,)
    ).fetchone()
    conn.close()
    return row


# --- Keywords ---

def get_keywords(user_id: int) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM keywords WHERE user_id = ?", (user_id,)
    ).fetchall()
    conn.close()
    return rows


def create_keyword(user_id: int, keyword: str, message: str) -> int:
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO keywords (user_id, keyword, message) VALUES (?, ?, ?)",
        (user_id, keyword, message),
    )
    conn.commit()
    kw_id = cur.lastrowid
    conn.close()
    return kw_id


# --- Replies ---

def get_replies(user_id: int) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM replies WHERE user_id = ?", (user_id,)
    ).fetchall()
    conn.close()
    return rows


def create_reply(user_id: int, text: str) -> int:
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO replies (user_id, text) VALUES (?, ?)",
        (user_id, text),
    )
    conn.commit()
    reply_id = cur.lastrowid
    conn.close()
    return reply_id


# --- Subscriptions ---

def create_subscription(user_id: int, expires_at: str) -> int:
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO subscriptions (user_id, expires_at) VALUES (?, ?)",
        (user_id, expires_at),
    )
    conn.commit()
    sub_id = cur.lastrowid
    conn.close()
    return sub_id


def get_active_subscription(user_id: int):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM subscriptions WHERE user_id = ? AND active = 1 AND expires_at > datetime('now')",
        (user_id,),
    ).fetchone()
    conn.close()
    return row


# --- Bulk updates ---

def update_keywords(user_id: int, keywords: dict):
    conn = get_db()
    conn.execute("DELETE FROM keywords WHERE user_id = ?", (user_id,))
    for kw, msg in keywords.items():
        conn.execute(
            "INSERT INTO keywords (user_id, keyword, message) VALUES (?, ?, ?)",
            (user_id, kw, msg),
        )
    conn.commit()
    conn.close()


def update_replies(user_id: int, replies: list):
    conn = get_db()
    conn.execute("DELETE FROM replies WHERE user_id = ?", (user_id,))
    for text in replies:
        conn.execute(
            "INSERT INTO replies (user_id, text) VALUES (?, ?)",
            (user_id, text),
        )
    conn.commit()
    conn.close()
