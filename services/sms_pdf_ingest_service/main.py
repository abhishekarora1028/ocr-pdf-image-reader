import os
from typing import Dict, Optional
from urllib.parse import urlparse

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl

PARSER_SERVICE_URL = os.environ.get("PARSER_SERVICE_URL", "http://localhost:8000")


class SmsPdfPayload(BaseModel):
    from_number: Optional[str] = None
    message_sid: Optional[str] = None
    body: Optional[str] = None
    pdf_url: HttpUrl


app = FastAPI(title="SMS PDF Ingest Service")


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/webhooks/twilio/pdf")
def ingest_sms_pdf(payload: SmsPdfPayload) -> Dict[str, int]:
    try:
        pdf_response = requests.get(str(payload.pdf_url), timeout=30)
        pdf_response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch PDF URL: {exc}") from exc

    content_type = (pdf_response.headers.get("content-type") or "").split(";")[0].strip()
    parsed_path = urlparse(str(payload.pdf_url)).path
    filename = os.path.basename(parsed_path) or "sms_receipt.pdf"

    if content_type and content_type != "application/pdf" and not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Provided URL does not look like a PDF")

    files = {
        "file": (
            filename,
            pdf_response.content,
            "application/pdf",
        )
    }
    data = {
        "sender": payload.from_number,
        "subject": payload.body,
        "source_message_id": payload.message_sid,
    }

    parse_endpoint = f"{PARSER_SERVICE_URL.rstrip('/')}/parse/receipt"

    try:
        parse_response = requests.post(parse_endpoint, files=files, data=data, timeout=30)
        parse_response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Failed to send PDF to parser service: {exc}") from exc

    return parse_response.json()
