import argparse
import io
import json
import re
from typing import Dict, Optional

try:
    from fastapi import FastAPI, File, Form, UploadFile
except ImportError:  # pragma: no cover
    FastAPI = None  # type: ignore
    File = Form = UploadFile = None  # type: ignore

from services.common.db import DEFAULT_DB_PATH, get_conn, init_db

PARSER_VERSION = "1.0.0"


def _extract_text_from_pdf(blob: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(io.BytesIO(blob))
        return "\n".join([(page.extract_text() or "") for page in reader.pages]).strip()
    except Exception as exc:
        return f"[pdf_text_extraction_unavailable] {exc}"


def _extract_text_from_image(blob: bytes) -> str:
    try:
        from PIL import Image  # type: ignore
        import pytesseract  # type: ignore

        image = Image.open(io.BytesIO(blob))
        return pytesseract.image_to_string(image).strip()
    except Exception as exc:
        return f"[ocr_unavailable] {exc}"


def _heuristic_parse(text: str, attachment_name: str, mime_type: str) -> Dict[str, Optional[str]]:
    total_match = re.search(r"(?:total|amount)\s*[:$]?\s*([0-9]+(?:\.[0-9]{2})?)", text, re.IGNORECASE)
    date_match = re.search(r"\b(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})\b", text)

    first_nonempty = next((line.strip() for line in text.splitlines() if line.strip()), None)

    return {
        "attachment_name": attachment_name,
        "mime_type": mime_type,
        "vendor": first_nonempty,
        "date": date_match.group(1) if date_match else None,
        "total": total_match.group(1) if total_match else None,
        "raw_text": text,
    }


def _parse_blob(blob: bytes, attachment_name: str, mime_type: str) -> Dict[str, Optional[str]]:
    if mime_type == "application/pdf" or attachment_name.lower().endswith(".pdf"):
        text = _extract_text_from_pdf(blob)
    else:
        text = _extract_text_from_image(blob)
    return _heuristic_parse(text, attachment_name, mime_type)


def parse_and_store_attachment(
    blob: bytes,
    attachment_name: str,
    mime_type: str,
    db_path: str,
    sender: Optional[str] = None,
    subject: Optional[str] = None,
    source_message_id: Optional[str] = None,
) -> Dict[str, int]:
    parsed_json = _parse_blob(blob, attachment_name, mime_type)

    with get_conn(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO raw_receipts (
                message_id, sender, subject, attachment_name, mime_type, attachment_blob, status
            ) VALUES (?, ?, ?, ?, ?, ?, 'parsed')
            """,
            (source_message_id, sender, subject, attachment_name, mime_type, blob),
        )
        raw_receipt_id = int(cursor.lastrowid)

        parsed_cursor = conn.execute(
            """
            INSERT INTO parsed_receipts (raw_receipt_id, parser_version, parsed_json)
            VALUES (?, ?, ?)
            """,
            (raw_receipt_id, PARSER_VERSION, json.dumps(parsed_json)),
        )

    return {"raw_receipt_id": raw_receipt_id, "parsed_receipt_id": int(parsed_cursor.lastrowid)}


def parse_pending_receipts(db_path: str) -> int:
    parsed_count = 0
    with get_conn(db_path) as conn:
        pending = conn.execute(
            """
            SELECT id, attachment_name, mime_type, attachment_blob
            FROM raw_receipts
            WHERE status = 'pending'
            ORDER BY id ASC
            """
        ).fetchall()

        for row in pending:
            parsed = _parse_blob(row["attachment_blob"], row["attachment_name"], row["mime_type"])
            conn.execute(
                """
                INSERT INTO parsed_receipts (raw_receipt_id, parser_version, parsed_json)
                VALUES (?, ?, ?)
                """,
                (row["id"], PARSER_VERSION, json.dumps(parsed)),
            )
            conn.execute(
                """
                UPDATE raw_receipts
                SET status = 'parsed', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (row["id"],),
            )
            parsed_count += 1

    return parsed_count


def create_app(db_path: str = DEFAULT_DB_PATH):
    if FastAPI is None:
        raise RuntimeError("fastapi is required to run the HTTP parser service")

    app = FastAPI(title="Receipt Parse Service")

    @app.on_event("startup")
    def startup() -> None:
        init_db(db_path)

    @app.post("/parse/receipt")
    async def parse_receipt(
        file: UploadFile = File(...),
        sender: Optional[str] = Form(default=None),
        subject: Optional[str] = Form(default=None),
        source_message_id: Optional[str] = Form(default=None),
    ) -> Dict[str, int]:
        blob = await file.read()
        return parse_and_store_attachment(
            blob=blob,
            attachment_name=file.filename or "uploaded_receipt",
            mime_type=file.content_type or "application/octet-stream",
            db_path=db_path,
            sender=sender,
            subject=subject,
            source_message_id=source_message_id,
        )

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Service 2: parse receipt files and store JSON")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    init_db(args.db_path)
    count = parse_pending_receipts(args.db_path)
    print(f"Parsed {count} receipt(s) and stored JSON in parsed_receipts")


app = create_app() if FastAPI is not None else None

if __name__ == "__main__":
    main()
