import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator

DEFAULT_DB_PATH = os.environ.get("RECEIPTS_DB_PATH", os.path.join("data", "receipts.db"))


@contextmanager
def get_conn(db_path: str = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT,
                sender TEXT,
                subject TEXT,
                attachment_name TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                attachment_blob BLOB NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS parsed_receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_receipt_id INTEGER NOT NULL,
                parser_version TEXT NOT NULL,
                parsed_json TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(raw_receipt_id) REFERENCES raw_receipts(id)
            )
            """
        )
