import argparse
import email
import imaplib
import os
from email.message import Message
from pathlib import Path
from typing import Iterable, List, Tuple

from services.common.db import DEFAULT_DB_PATH, get_conn, init_db

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp"}


def _collect_receipt_attachments(msg: Message) -> List[Tuple[str, str, bytes]]:
    attachments: List[Tuple[str, str, bytes]] = []
    for part in msg.walk():
        filename = part.get_filename()
        if not filename:
            continue

        extension = Path(filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            continue

        payload = part.get_payload(decode=True)
        if not payload:
            continue

        attachments.append((filename, part.get_content_type(), payload))
    return attachments


def _save_attachments(msg: Message, attachments: Iterable[Tuple[str, str, bytes]], db_path: str) -> int:
    message_id = msg.get("Message-ID")
    sender = msg.get("From")
    subject = msg.get("Subject")

    inserted = 0
    with get_conn(db_path) as conn:
        for attachment_name, mime_type, blob in attachments:
            conn.execute(
                """
                INSERT INTO raw_receipts (
                    message_id, sender, subject, attachment_name, mime_type, attachment_blob, status
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending')
                """,
                (message_id, sender, subject, attachment_name, mime_type, blob),
            )
            inserted += 1
    return inserted


def ingest_local_eml(eml_dir: str, db_path: str) -> int:
    total = 0
    for path in sorted(Path(eml_dir).glob("*.eml")):
        with open(path, "rb") as f:
            msg = email.message_from_binary_file(f)
        attachments = _collect_receipt_attachments(msg)
        total += _save_attachments(msg, attachments, db_path)
    return total


def ingest_imap(db_path: str) -> int:
    host = os.environ.get("IMAP_HOST")
    username = os.environ.get("IMAP_USER")
    password = os.environ.get("IMAP_PASSWORD")
    mailbox = os.environ.get("IMAP_MAILBOX", "INBOX")

    if not host or not username or not password:
        raise RuntimeError("IMAP_HOST, IMAP_USER, and IMAP_PASSWORD must be set for source=imap")

    total = 0
    with imaplib.IMAP4_SSL(host) as mail:
        mail.login(username, password)
        mail.select(mailbox)
        typ, data = mail.search(None, "ALL")
        if typ != "OK":
            raise RuntimeError("Failed to search mailbox")

        for msg_id in data[0].split():
            fetch_type, msg_data = mail.fetch(msg_id, "(RFC822)")
            if fetch_type != "OK":
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            attachments = _collect_receipt_attachments(msg)
            total += _save_attachments(msg, attachments, db_path)

    return total


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Service 1: fetch emails and extract receipt attachments")
    parser.add_argument("--source", choices=["local", "imap"], default="local")
    parser.add_argument("--eml-dir", default="sample_emails", help="Directory with .eml files for local source")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    init_db(args.db_path)

    if args.source == "local":
        count = ingest_local_eml(args.eml_dir, args.db_path)
    else:
        count = ingest_imap(args.db_path)

    print(f"Saved {count} attachment(s) into raw_receipts")


if __name__ == "__main__":
    main()
