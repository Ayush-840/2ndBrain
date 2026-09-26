"""WhatsApp Cloud API capture adapter.

This file only knows how to talk to Meta's API and pull bytes out of it.
It does NOT parse PDFs itself — once we have the raw bytes we hand them
to the same pdf.py / markdown.py logic the rest of the app already uses,
so there is only ever one PDF parser in the repo.

Three jobs, in order:
  1. verify_signature()  — reject anything Meta didn't send
  2. parse_webhook_event() — walk Meta's nested JSON into WhatsAppMessage
  3. message_to_capture()  — download media bytes → a normal Capture
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass

import requests

from backend.config import settings
from backend.ingestion.base import Capture

logger = logging.getLogger(__name__)

# Media types we turn into Captures. Plain text is handled separately
# because it carries corrections rather than documents.
MEDIA_TYPES = ("document", "image", "video", "audio")


@dataclass
class WhatsAppMessage:
    """One inbound message, flattened out of Meta's webhook payload."""

    message_id: str
    sender: str
    msg_type: str  # "document", "image", "text", ...
    media_id: str | None = None
    caption: str | None = None
    text: str | None = None
    filename: str | None = None
    mime_type: str | None = None
    timestamp: str | None = None
    reply_to_id: str | None = None  # set when this message is a reply


class WhatsAppClient:
    """Thin wrapper around the handful of Cloud API calls we actually need."""

    def __init__(
        self,
        access_token: str | None = None,
        phone_number_id: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
    ):
        self.access_token = access_token if access_token is not None else settings.whatsapp_access_token
        self.phone_number_id = (
            phone_number_id if phone_number_id is not None else settings.whatsapp_phone_number_id
        )
        self.base_url = base_url or f"https://graph.facebook.com/{settings.whatsapp_api_version}"
        self.timeout = timeout

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

    def download_media(self, media_id: str) -> bytes:
        """Resolve a media id to a short-lived URL (~5 min), then fetch bytes.

        Both requests need the access token — the download URL is NOT public.
        """
        meta = requests.get(f"{self.base_url}/{media_id}", headers=self._headers(), timeout=self.timeout)
        meta.raise_for_status()
        media_url = meta.json()["url"]

        file_response = requests.get(media_url, headers=self._headers(), timeout=self.timeout)
        file_response.raise_for_status()
        return file_response.content

    def send_text(self, to: str, body: str) -> bool:
        """Send a plain-text message. Returns True if Meta accepted it."""
        if not self.access_token or not self.phone_number_id:
            logger.warning("WhatsApp not configured — skipping send to %s", to)
            return False
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }
        try:
            resp = requests.post(
                f"{self.base_url}/{self.phone_number_id}/messages",
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
            if not resp.ok:
                logger.warning("WhatsApp send failed (%s): %s", resp.status_code, resp.text[:300])
                return False
            return True
        except requests.RequestException as exc:
            logger.warning("WhatsApp send error: %s", exc)
            return False


def verify_signature(app_secret: str, raw_body: bytes, signature_header: str) -> bool:
    """Verify Meta's X-Hub-Signature-256 header.

    HMAC-SHA256 over the RAW request bytes with the app secret as key.
    Must be computed before any JSON parsing — re-serializing changes bytes.
    """
    if not app_secret or not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.split("sha256=", 1)[1]
    return hmac.compare_digest(expected, provided)


def parse_webhook_event(payload: dict, allowed_sender: str | None = None) -> list[WhatsAppMessage]:
    """Flatten Meta's webhook JSON into WhatsAppMessage objects.

    Walks every entry/change/message (Meta batches them). Anything that
    isn't a message — read receipts, status updates, plain chit-chat we
    don't handle — is skipped on purpose.
    """
    messages: list[WhatsAppMessage] = []

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                sender = message.get("from") or ""
                if allowed_sender and sender != allowed_sender:
                    # Not you. This is a personal system, not a public bot.
                    continue

                msg_type = message.get("type") or ""
                reply_to = (message.get("context") or {}).get("id")

                if msg_type == "text":
                    body = message.get("text", {})
                    messages.append(
                        WhatsAppMessage(
                            message_id=message.get("id", ""),
                            sender=sender,
                            msg_type="text",
                            text=body.get("body"),
                            timestamp=message.get("timestamp"),
                            reply_to_id=reply_to,
                        )
                    )
                elif msg_type in MEDIA_TYPES:
                    media_block = message.get(msg_type) or {}
                    messages.append(
                        WhatsAppMessage(
                            message_id=message.get("id", ""),
                            sender=sender,
                            msg_type=msg_type,
                            media_id=media_block.get("id"),
                            caption=media_block.get("caption"),
                            filename=media_block.get("filename"),
                            mime_type=media_block.get("mime_type"),
                            timestamp=message.get("timestamp"),
                            reply_to_id=reply_to,
                        )
                    )
                # Other types (location, contacts, reactions, ...) ignored.

    return messages


def extract_text_from_media(
    data: bytes,
    mime_type: str | None = None,
    filename: str | None = None,
) -> str:
    """Pull searchable text out of downloaded media bytes.

    PDFs go through PyMuPDF (same as the vault PDF path). Text-ish files
    are decoded directly. Images have no text layer — the caller decides
    what to do with the caption instead.
    """
    suffix = (filename or "").lower().rsplit(".", 1)[-1]
    is_pdf = (
        (mime_type or "").startswith("application/pdf")
        or suffix == "pdf"
        or data[:5] == b"%PDF-"
    )
    if is_pdf:
        import fitz  # pymupdf

        try:
            doc = fitz.open(stream=data, filetype="pdf")
            pages = [page.get_text() for page in doc]
            doc.close()
            return "\n\n".join(pages).strip()
        except Exception as exc:  # noqa: BLE001 — corrupt PDF should not kill the webhook
            logger.warning("PDF text extraction failed: %s", exc)
            return ""

    if suffix in ("md", "markdown", "txt", "csv", "json", "log") or (
        mime_type and mime_type.startswith("text/")
    ):
        return data.decode("utf-8", errors="replace").strip()

    return ""


def capture_from_message(msg: WhatsAppMessage, *, raw_bytes: bytes | None = None) -> Capture | None:
    """Build a Capture from a message plus (for media) its downloaded bytes.

    Pure function — no network calls — so callers control when the media
    download happens (the webhook downloads once and keeps the bytes for
    both the pipeline and the encrypted blob store).
    """
    if msg.msg_type == "text":
        text = (msg.text or "").strip()
        if not text:
            return None
        return Capture(
            content=text,
            source_path=f"whatsapp/{msg.message_id}",
            source_type="whatsapp",
            metadata={
                "channel": "whatsapp",
                "wamid": msg.message_id,
                "kind": "text",
                "sender": msg.sender,
            },
            caption=msg.caption,
            sender_message_id=msg.message_id,
        )

    if not msg.media_id or raw_bytes is None:
        return None

    extracted = extract_text_from_media(raw_bytes, msg.mime_type, msg.filename)
    caption = (msg.caption or "").strip()
    title = msg.filename or f"whatsapp-{msg.message_id}"

    # Content needs at least one line for the chunker. Prefer the document's
    # own text, then the caption the user typed, then a placeholder.
    parts = [p for p in (extracted.strip() if extracted else "", caption) if p]
    content = "\n\n".join(parts) or f"Captured document: {title}"

    metadata: dict = {
        "channel": "whatsapp",
        "wamid": msg.message_id,
        "kind": msg.msg_type,
        "sender": msg.sender,
        "filename": msg.filename,
        "mime_type": msg.mime_type,
        "media_id": msg.media_id,
        "has_caption": bool(caption),
    }

    return Capture(
        content=content,
        source_path=f"whatsapp/{msg.message_id}",
        source_type="whatsapp",
        metadata=metadata,
        caption=caption or None,
        sender_message_id=msg.message_id,
    )


def message_to_capture(msg: WhatsAppMessage, client: WhatsAppClient) -> Capture | None:
    """Download the media (if any) and turn the message into a Capture."""
    if msg.msg_type != "text":
        if not msg.media_id:
            return None
        try:
            raw_bytes = client.download_media(msg.media_id)
        except Exception as exc:  # noqa: BLE001 — a dead media id must not break the batch
            logger.warning("Failed to download WhatsApp media %s: %s", msg.media_id, exc)
            return None
        return capture_from_message(msg, raw_bytes=raw_bytes)

    return capture_from_message(msg)
