"""WhatsApp webhook routes — Phase 6 capture channel.

Two routes, matching what Meta requires:
  GET  — the one-time verification handshake (echo hub.challenge as plain text)
  POST — actual incoming messages (signature-checked, then acked <5s)

Heavy work (media download, embedding, LLM extraction) runs as a background
task so Meta always gets its 200 quickly. Meta retries non-200 deliveries for
up to 7 days, so every delivery is deduped on WhatsApp's message id (wamid).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

from backend.api.routes_ingest import get_pipeline
from backend.config import settings
from backend.enrichment.purpose import parse_expiry_date, tag_text
from backend.ingestion.whatsapp import (
    WhatsAppClient,
    WhatsAppMessage,
    capture_from_message,
    parse_webhook_event,
    verify_signature,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest/whatsapp", tags=["whatsapp"])

MAX_PROCESSED_IDS = 2000
CORRECTION_WINDOW_SECONDS = 30 * 60

# wamid → (doc_id, unix_ts) for documents this process has captured.
# The wamid→doc mapping also lives in the on-disk ledger so corrections
# still land after a restart; the timestamps only guard the "reply without
# quoting a message" fallback.
_seen_docs: dict[str, tuple[str, float]] = {}
_last_doc_by_sender: dict[str, tuple[str, float]] = {}


# ── On-disk ledger (idempotency) ─────────────────────────────────────


def _ledger_path() -> Path:
    return Path(settings.processed_ids_path)


def _load_ledger() -> dict:
    path = _ledger_path()
    if path.exists():
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                data.setdefault("processed", [])
                data.setdefault("docs", {})
                return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read webhook ledger %s: %s", path, exc)
    return {"processed": [], "docs": {}}


def _save_ledger(ledger: dict) -> None:
    path = _ledger_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Cap the id list so the file can't grow forever.
        ledger["processed"] = ledger["processed"][-MAX_PROCESSED_IDS:]
        path.write_text(json.dumps(ledger, indent=2))
    except OSError as exc:
        logger.warning("Could not write webhook ledger %s: %s", path, exc)


def _is_processed(wamid: str) -> bool:
    return wamid in _seen_docs


def _mark_processed(wamid: str, doc_id: str, ledger: dict) -> None:
    _seen_docs[wamid] = (doc_id, time.time())
    if wamid not in ledger["processed"]:
        ledger["processed"].append(wamid)
    if doc_id:
        ledger["docs"][wamid] = doc_id


def _warm_seen_cache() -> None:
    """Load the on-disk ledger into memory once per process."""
    if _seen_docs:
        return
    ledger = _load_ledger()
    now = time.time()
    for wamid, doc_id in ledger["docs"].items():
        _seen_docs[wamid] = (doc_id, now)


# ── Routes ───────────────────────────────────────────────────────────


@router.get("/webhook")
def verify_webhook(request: Request):
    """Meta's one-time handshake. Must reply with the raw challenge string."""
    params = request.query_params
    if (
        params.get("hub.mode") == "subscribe"
        and settings.whatsapp_verify_token
        and params.get("hub.verify_token") == settings.whatsapp_verify_token
    ):
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(status_code=403, detail="verification failed")


@router.post("/webhook")
async def receive_webhook(request: Request, background: BackgroundTasks):
    """Inbound message events. Verify → dedupe → ack → process in background."""
    raw_body = await request.body()

    signature = request.headers.get("X-Hub-Signature-256", "")
    if settings.whatsapp_app_secret:
        if not verify_signature(settings.whatsapp_app_secret, raw_body, signature):
            logger.warning("Rejected webhook: bad or missing signature")
            raise HTTPException(status_code=401, detail="bad signature")
    elif not settings.whatsapp_allow_unsigned:
        # Fail closed: an unsigned webhook would let anyone inject documents.
        logger.warning("Rejected webhook: no app secret configured (fail closed)")
        raise HTTPException(status_code=401, detail="webhook signature verification not configured")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid JSON") from exc

    messages = parse_webhook_event(payload, settings.whatsapp_allowed_sender or None)
    if not messages:
        # Status updates, unknown types, or other senders — nothing to do.
        return {"status": "received", "accepted": 0}

    _warm_seen_cache()
    ledger = _load_ledger()
    new_messages: list[WhatsAppMessage] = []
    for msg in messages:
        if not msg.message_id or msg.message_id in ledger["processed"]:
            continue  # Meta is retrying a delivery we already handled
        ledger["processed"].append(msg.message_id)
        ledger["docs"].setdefault(msg.message_id, "")  # placeholder until processed
        new_messages.append(msg)

    # Persist BEFORE acking: a crash after 200 must not cause a re-ingest loop.
    _save_ledger(ledger)

    if new_messages:
        for msg in new_messages:
            _pending[msg.message_id] = msg  # picked up by the background task
        background.add_task(_process_messages, [m.message_id for m in new_messages])

    return {"status": "received", "accepted": len(new_messages)}


# ── Background processing ────────────────────────────────────────────

# Parsed messages waiting for the background task. Holding them here (rather
# than re-hitting Meta) keeps the request handler's only job: verify, dedupe, ack.
_pending: dict[str, WhatsAppMessage] = {}


def _process_messages(message_ids: list[str]) -> None:
    """Download → ingest → Document node → confirmation reply."""
    ledger = _load_ledger()
    pipeline = get_pipeline()
    client = WhatsAppClient()

    for message_id in message_ids:
        msg = _pending.pop(message_id, None)
        if msg is None:
            continue
        try:
            if msg.msg_type == "text":
                _handle_text_message(pipeline, client, msg, ledger)
            else:
                _handle_media_message(pipeline, client, msg, ledger)
        except Exception:
            logger.exception("Failed processing WhatsApp message %s", message_id)
        finally:
            _save_ledger(ledger)


def _handle_media_message(pipeline, client: WhatsAppClient, msg: WhatsAppMessage, ledger: dict) -> None:
    if not msg.media_id:
        return
    try:
        raw_bytes = client.download_media(msg.media_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Media download failed for %s: %s", msg.message_id, exc)
        return

    capture = capture_from_message(msg, raw_bytes=raw_bytes)
    if capture is None:
        return

    result = pipeline.ingest_document(
        capture,
        filename=msg.filename,
        mime_type=msg.mime_type,
        blob_bytes=raw_bytes,
        source_channel="whatsapp",
    )
    doc_id = result.get("doc_id", "")
    if not doc_id:
        return

    _mark_processed(msg.message_id, doc_id, ledger)
    if msg.sender:
        _last_doc_by_sender[msg.sender] = (doc_id, time.time())

    _send_confirmation(client, msg, result)


def _handle_text_message(pipeline, client: WhatsAppClient, msg: WhatsAppMessage, ledger: dict) -> None:
    """A plain text message from the owner is a correction of a purpose."""
    text = (msg.text or "").strip()
    if not text:
        return

    doc_id = _correction_target(msg, ledger)
    if not doc_id:
        logger.info("Ignoring WhatsApp text from %s: no document to correct", msg.sender)
        return

    updated = _apply_correction(pipeline, doc_id, text)
    _mark_processed(msg.message_id, doc_id, ledger)

    if updated and client and msg.sender:
        client.send_text(
            to=msg.sender,
            body=(
                f"Updated: {updated['title']}\n"
                f"Now tagged as: {', '.join(updated['purpose_tags'])}\n"
                f"Reason: {updated['usage_context']}"
            ),
        )


def _correction_target(msg: WhatsAppMessage, ledger: dict) -> str | None:
    """Which document is this text correcting?

    Quoted reply wins (Meta gives us the original wamid in context.id).
    Otherwise: the most recent document captured from this sender within
    the correction window — i.e. the confirmation they just received.
    """
    if msg.reply_to_id:
        doc_id = ledger["docs"].get(msg.reply_to_id)
        if doc_id:
            return doc_id
        cached = _seen_docs.get(msg.reply_to_id)
        if cached:
            return cached[0]

    last = _last_doc_by_sender.get(msg.sender)
    if last and time.time() - last[1] <= CORRECTION_WINDOW_SECONDS:
        return last[0]
    return None


def _apply_correction(pipeline, doc_id: str, correction_text: str) -> dict | None:
    """Supersede the document's purpose with the owner's own words."""
    old = pipeline.graph.get_document(doc_id)
    if old is None:
        return None

    new_tags = tag_text(correction_text)
    purpose_tags = old.get("purpose_tags", []) if new_tags == ["other"] else new_tags
    valid_until = parse_expiry_date(correction_text) or old.get("valid_until")

    return pipeline.graph.correct_document(
        doc_id,
        usage_context=correction_text,
        purpose_tags=purpose_tags,
        valid_until=valid_until,
    )


def _send_confirmation(client: WhatsAppClient, msg: WhatsAppMessage, result: dict) -> None:
    """One-line 'what I saved and why' so a wrong guess can be fixed at once."""
    if not msg.sender:
        return

    tags = ", ".join(result.get("purpose_tags") or []) or "untagged"
    lines = [
        f"Saved: {result.get('title', 'document')}",
        f"Tagged as: {tags}",
    ]
    if result.get("usage_context"):
        lines.append(f"Context: {result['usage_context']}")
    if result.get("valid_until"):
        lines.append(f"Relevant until: {str(result['valid_until'])[:10]}")
    lines.append("Reply to correct this if it's wrong.")

    client.send_text(to=msg.sender, body="\n".join(lines))
