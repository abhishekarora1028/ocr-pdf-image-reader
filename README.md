# OCR PDF/Image Receipt Reader (Split Services)

This repository is split into **two independent services**:

1. **Email Fetch Service** (`services/email_fetch_service`)
   - Connects to an IMAP inbox (or reads local `.eml` files for dev).
   - Extracts receipt attachments (`.pdf`, `.png`, `.jpg`, `.jpeg`, `.tiff`, `.bmp`).
   - Stores raw attachments + email metadata in SQLite.

2. **Receipt Parse Service** (`services/receipt_parse_service`)
   - Pulls pending raw attachments from SQLite.
   - Attempts to parse PDF/image content into text.
   - Produces structured JSON and stores it in SQLite.

## Project structure

- `services/common/db.py` shared DB schema and helpers
- `services/email_fetch_service/main.py` email/attachment ingestion
- `services/receipt_parse_service/main.py` parsing + JSON persistence

## Quick start

```bash
python -m services.email_fetch_service.main --source local --eml-dir sample_emails
python -m services.receipt_parse_service.main
```

Database path defaults to `./data/receipts.db` (override with `RECEIPTS_DB_PATH`).

## Optional dependencies for richer parsing

- `pypdf` for better PDF text extraction
- `pillow` + `pytesseract` for OCR on images

Without optional dependencies, the parser still writes JSON metadata records.
