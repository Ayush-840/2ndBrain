# Reference Implementation — WhatsApp Capture Adapter

This is written the same way the rest of 2ndBrain is written: small files, one job each, no clever abstractions, plain `requests` calls instead of a heavy SDK — "tools a student can own and explain," matching the project's own stated design philosophy. Drop these three files into the existing `backend/` package; nothing else in the repo needs to change.

---

## `backend/config.py` — add these settings

```python
# Added to the existing Pydantic Settings class.
# Keep them optional so the app still boots fine if you're not using WhatsApp yet.

whatsapp_access_token: str | None = Field(default=None, env="BRAIN_WHATSAPP_ACCESS_TOKEN")
whatsapp_phone_number_id: str | None = Field(default=None, env="BRAIN_WHATSAPP_PHONE_NUMBER_ID")
whatsapp_verify_token: str | None = Field(default=None, env="BRAIN_WHATSAPP_VERIFY_TOKEN")
whatsapp_app_secret: str | None = Field(default=None, env="BRAIN_WHATSAPP_APP_SECRET")
whatsapp_allowed_sender: str | None = Field(default=None, env="BRAIN_WHATSAPP_ALLOWED_SENDER")
```

---

## `backend/ingestion/whatsapp.py`

```python
"""
Turns WhatsApp Cloud API webhook events into Captures.

This file only knows how to talk to Meta's API and pull bytes out of it.
It does NOT parse PDFs itself - once we have the raw bytes we hand them
to the same pdf.py / markdown.py logic the rest of the app already uses.
That way we're not maintaining two PDF parsers.
"""

import hashlib
import hmac
import requests

from backend.config import get_settings
from backend.ingestion.base import Capture

GRAPH_API_VERSION = "v21.0"


class WhatsAppClient:
    """Thin wrapper around the handful of Cloud API calls we actually need."""

    def __init__(self, access_token: str, phone_number_id: str):
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.base_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

    def _headers(self):
        return {"Authorization": f"Bearer {self.access_token}"}

    def download_media(self, media_id: str) -> bytes:
        # Step 1: ask Meta for the temporary download URL for this media id.
        meta = requests.get(f"{self.base_url}/{media_id}", headers=self._headers())
        meta.raise_for_status()
        media_url = meta.json()["url"]

        # Step 2: actually download the file bytes from that URL.
        file_response = requests.get(media_url, headers=self._headers())
        file_response.raise_for_status()
        return file_response.content

    def send_text(self, to: str, body: str) -> None:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }
        requests.post(
            f"{self.base_url}/{self.phone_number_id}/messages",
            headers=self._headers(),
            json=payload,
        )


def verify_signature(app_secret: str, raw_body: bytes, signature_header: str) -> bool:
    """
    Meta signs every webhook POST with X-Hub-Signature-256.
    We recompute it ourselves and compare - if it doesn't match, or the
    header is missing, we reject the request before touching anything else.
    """
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.split("sha256=", 1)[1]
    return hmac.compare_digest(expected, provided)


def parse_webhook_event(payload: dict, client: WhatsAppClient) -> list[Capture]:
    """
    Walks Meta's (fairly deeply nested) webhook JSON shape and turns any
    document/image message into a Capture. Anything else (plain text,
    read receipts, status updates) is ignored on purpose for now.
    """
    settings = get_settings()
    captures: list[Capture] = []

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):

                sender = message.get("from")
                if settings.whatsapp_allowed_sender and sender != settings.whatsapp_allowed_sender:
                    # Not you. Ignore it - this is a personal system, not a public bot.
                    continue

                msg_type = message.get("type")
                if msg_type not in ("document", "image"):
                    continue

                media_block = message[msg_type]
                media_bytes = client.download_media(media_block["id"])

                captures.append(Capture(
                    source_type="whatsapp",
                    raw_content=media_bytes,
                    caption=media_block.get("caption"),
                    sender_message_id=message.get("id"),
                ))

    return captures
```

---

## `backend/api/routes_ingest_whatsapp.py`

```python
"""
FastAPI routes for the WhatsApp webhook.
Two routes, matching what Meta requires:
  GET  - the one-time verification handshake
  POST - actual incoming messages
"""

from fastapi import APIRouter, Request, Response, HTTPException

from backend.config import get_settings
from backend.ingestion.whatsapp import WhatsAppClient, parse_webhook_event, verify_signature
from backend.pipeline import ingest_captures  # existing orchestrator function

router = APIRouter()

# Simple in-memory set so we don't process the same WhatsApp message twice
# if Meta retries a delivery. Fine for a single-user, single-process app.
_seen_message_ids: set[str] = set()


@router.get("/ingest/whatsapp/webhook")
def verify_webhook(request: Request):
    settings = get_settings()
    params = request.query_params
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == settings.whatsapp_verify_token
    ):
        # Meta expects the raw challenge string back, not JSON.
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(status_code=403, detail="verification failed")


@router.post("/ingest/whatsapp/webhook")
async def receive_webhook(request: Request):
    settings = get_settings()
    raw_body = await request.body()

    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(settings.whatsapp_app_secret, raw_body, signature):
        raise HTTPException(status_code=401, detail="bad signature")

    payload = await request.json()
    client = WhatsAppClient(settings.whatsapp_access_token, settings.whatsapp_phone_number_id)

    captures = parse_webhook_event(payload, client)

    new_captures = []
    for capture in captures:
        if capture.sender_message_id in _seen_message_ids:
            continue  # already handled this one, Meta is just retrying delivery
        _seen_message_ids.add(capture.sender_message_id)
        new_captures.append(capture)

    if new_captures:
        # Hand off to the existing pipeline (chunk -> embed -> extract -> store).
        # This is the SAME function markdown/pdf ingestion already calls.
        results = ingest_captures(new_captures, extract=True)

        for capture, result in zip(new_captures, results):
            confirmation = (
                f"Saved: {result.title}\n"
                f"Tagged as: {result.usage_context}\n"
                f"Reply to correct this if it's wrong."
            )
            client.send_text(to=settings.whatsapp_allowed_sender, body=confirmation)

    # Meta just needs a 200 within 5 seconds - it doesn't care what's in the body.
    return {"status": "received"}
```

---

## Wiring it up

```python
# backend/main.py - one extra line alongside the other routers
from backend.api import routes_ingest_whatsapp
app.include_router(routes_ingest_whatsapp.router)
```

That's the whole integration. No new database, no new job queue, no new frontend framework - it plugs into `ingest_captures(...)`, the same function the vault/PDF ingestion path already calls, which is exactly why the rest of the system (chunking, embeddings, graph, retrieval) needs zero changes to support a new capture channel.
