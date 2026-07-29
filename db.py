import sqlite3
from contextlib import contextmanager
from config import DB_PATH


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            email          TEXT NOT NULL UNIQUE,
            password_hash  TEXT NOT NULL,
            game_username  TEXT UNIQUE,
            robux          INTEGER NOT NULL DEFAULT 0,
            is_admin       INTEGER NOT NULL DEFAULT 0,
            created_at     TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS admin_stock (
            id        INTEGER PRIMARY KEY CHECK (id = 1),
            robux     INTEGER NOT NULL DEFAULT 10000
        );

        CREATE TABLE IF NOT EXISTS addresses (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            address         TEXT NOT NULL,
            reference       TEXT NOT NULL UNIQUE,
            vm_type         TEXT NOT NULL,
            gateway_id      TEXT NOT NULL,
            user_id         INTEGER NOT NULL,
            robux_amount    INTEGER NOT NULL,
            usdt_amount     TEXT NOT NULL,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            reference       TEXT NOT NULL UNIQUE,
            user_id         INTEGER NOT NULL,
            usdt_amount     TEXT NOT NULL,
            robux_amount    INTEGER NOT NULL,
            address         TEXT,
            tx_hash         TEXT,
            blockchain      TEXT,
            status          TEXT NOT NULL DEFAULT 'PENDING',
            net_amount      TEXT,
            error_message   TEXT,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            confirmed_at    TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        INSERT OR IGNORE INTO admin_stock (id, robux) VALUES (1, 10000);
    """)
    conn.commit()
    conn.close()
