# OCR PDF/Image Receipt Reader (Service-Oriented)

This project now contains **three services** that work together to ingest receipts, parse data, and store results in SQLite.

## Services overview

### 1) Email Fetch Service
**Module:** `services.email_fetch_service.main`  
Fetches `.eml` or IMAP emails, extracts receipt attachments, and stores raw files in `raw_receipts` with `pending` status.

### 2) Receipt Parse Service
**Module:** `services.receipt_parse_service.main`  
Parses pending receipts from DB (CLI mode) or accepts uploaded receipts over HTTP (API mode), then stores parsed JSON in `parsed_receipts`.

### 3) SMS PDF Ingest Service (new)
**Module:** `services.sms_pdf_ingest_service.main`  
Receives SMS webhook-like payload with a `pdf_url`, downloads the PDF, then forwards it to the Receipt Parse Service API for parsing + persistence.

---

## Endpoints

### Receipt Parse Service (HTTP API)
Run (default port `8000`):

```bash
uvicorn services.receipt_parse_service.main:app --host 0.0.0.0 --port 8000
```

Endpoints:

- `GET /health`
- `POST /parse/receipt` (multipart/form-data)
  - `file` (required): PDF/image file
  - `sender` (optional)
  - `subject` (optional)
  - `source_message_id` (optional)

Example:

```bash
curl -X POST http://localhost:8000/parse/receipt \
  -F "file=@sample.pdf;type=application/pdf" \
  -F "sender=+15551234567" \
  -F "subject=Forwarded from SMS" \
  -F "source_message_id=SM123"
```

### SMS PDF Ingest Service
Run (default port `8001`):

```bash
export PARSER_SERVICE_URL=http://localhost:8000
uvicorn services.sms_pdf_ingest_service.main:app --host 0.0.0.0 --port 8001
```

Endpoints:

- `GET /health`
- `POST /webhooks/twilio/pdf` (JSON body)

Example payload:

```json
{
  "from_number": "+15551234567",
  "message_sid": "SMXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
  "body": "Receipt from text message",
  "pdf_url": "https://example.com/receipt.pdf"
}
```

Example request:

```bash
curl -X POST http://localhost:8001/webhooks/twilio/pdf \
  -H "Content-Type: application/json" \
  -d '{
    "from_number": "+15551234567",
    "message_sid": "SMXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
    "body": "Receipt from text message",
    "pdf_url": "https://example.com/receipt.pdf"
  }'
```

### Email Fetch Service (CLI)

Local `.eml` mode:

```bash
python -m services.email_fetch_service.main --source local --eml-dir sample_emails
```

IMAP mode:

```bash
export IMAP_HOST=imap.example.com
export IMAP_USER=user@example.com
export IMAP_PASSWORD=secret
export IMAP_MAILBOX=INBOX
python -m services.email_fetch_service.main --source imap
```

### Receipt Parse Service (CLI batch mode)

```bash
python -m services.receipt_parse_service.main
```

---

## Database

Default DB path: `./data/receipts.db`  
Override via:

```bash
export RECEIPTS_DB_PATH=/path/to/receipts.db
```

Tables:
- `raw_receipts`: raw blobs + metadata + status
- `parsed_receipts`: parsed JSON linked by `raw_receipt_id`

---

## Local setup

### 1) Prerequisites
- Python 3.10+
- `pip`

### 2) Create virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3) Install dependencies

```bash
pip install fastapi uvicorn requests pypdf pillow pytesseract
```

> `pypdf`, `pillow`, and `pytesseract` improve parsing/OCR; parser still runs without them but text extraction may be limited.

### 4) Start services

Terminal A:
```bash
uvicorn services.receipt_parse_service.main:app --host 0.0.0.0 --port 8000
```

Terminal B:
```bash
export PARSER_SERVICE_URL=http://localhost:8000
uvicorn services.sms_pdf_ingest_service.main:app --host 0.0.0.0 --port 8001
```

Terminal C (optional email ingestion):
```bash
python -m services.email_fetch_service.main --source local --eml-dir sample_emails
```

### 5) Validate

```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
```

---

## Cloud VM setup (Ubuntu example)

### 1) Provision VM and install system deps

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

(For OCR support)
```bash
sudo apt install -y tesseract-ocr
```

### 2) Clone and install app

```bash
git clone <your-repo-url>
cd ocr-pdf-image-reader
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install fastapi uvicorn requests pypdf pillow pytesseract
```

### 3) Configure environment

```bash
export RECEIPTS_DB_PATH=/opt/ocr-pdf-image-reader/data/receipts.db
export PARSER_SERVICE_URL=http://127.0.0.1:8000
```

### 4) Run services with systemd (recommended)
Create two units:
- parser service: `uvicorn services.receipt_parse_service.main:app --host 0.0.0.0 --port 8000`
- sms ingest service: `uvicorn services.sms_pdf_ingest_service.main:app --host 0.0.0.0 --port 8001`

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable <parser-unit> <sms-unit>
sudo systemctl start <parser-unit> <sms-unit>
```

### 5) Network/security
- Open only required inbound ports (e.g. `8001` for webhook ingress).
- Keep parser service internal when possible (bind and firewall appropriately).
- If public-facing, place behind reverse proxy (Nginx/Caddy) with TLS.

---

## Notes

- The SMS ingest service is provider-agnostic but shaped for Twilio-forwarded webhook data.
- You can adapt field mapping (`from_number`, `message_sid`, `body`, `pdf_url`) to your actual webhook schema.
