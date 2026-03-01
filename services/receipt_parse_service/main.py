import argparse
import io
import json
import re
from typing import Dict, Optional

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
            if row["mime_type"] == "application/pdf" or row["attachment_name"].lower().endswith(".pdf"):
                text = _extract_text_from_pdf(row["attachment_blob"])
            else:
                text = _extract_text_from_image(row["attachment_blob"])

            parsed = _heuristic_parse(text, row["attachment_name"], row["mime_type"])
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Service 2: parse receipt files and store JSON")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    init_db(args.db_path)
    count = parse_pending_receipts(args.db_path)
    print(f"Parsed {count} receipt(s) and stored JSON in parsed_receipts")


if __name__ == "__main__":
    main()
