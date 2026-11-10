import sqlite3
from pathlib import Path


def connect_db(path="data/huellas.db"):
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS generations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prompt_id TEXT UNIQUE,
        profile TEXT,
        seed INTEGER,
        manifest_path TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT UNIQUE,
        filename TEXT,
        sha256 TEXT,
        profile TEXT,
        size_bytes INTEGER,
        generation_id INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(generation_id) REFERENCES generations(id)
    );

    CREATE INDEX IF NOT EXISTS idx_assets_profile
    ON assets(profile);

    CREATE INDEX IF NOT EXISTS idx_assets_hash
    ON assets(sha256);

    CREATE INDEX IF NOT EXISTS idx_generations_profile
    ON generations(profile);
    """)

    conn.commit()
    return conn