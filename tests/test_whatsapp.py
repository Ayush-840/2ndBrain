"""Unit tests for the WhatsApp adapter, purpose inference, and blob store."""

from __future__ import annotations

import hashlib
import hmac

import pytest

from backend.config import settings
from backend.enrichment.purpose import (
    infer_usage_context,
    parse_expiry_date,
    tag_text,
)
from backend.ingestion.whatsapp import (
    WhatsAppMessage,
    capture_from_message,
    extract_text_from_media,
    parse_webhook_event,
    verify_signature,
)
from backend.memory.blob_store import BlobStore

APP_SECRET = "test-app-secret"


# ── Signature verification (TRD §7) ──────────────────────────────────


class TestSignature:
    def test_valid_signature_accepted(self):
        body = b'{"entry":[]}'
        sig = "sha256=" + hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
        assert verify_signature(APP_SECRET, body, sig) is True

    def test_tampered_body_rejected(self):
        body = b'{"entry":[]}'
        sig = "sha256=" + hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
        assert verify_signature(APP_SECRET, b'{"entry":[1]}', sig) is False

    def test_missing_header_rejected(self):
        assert verify_signature(APP_SECRET, b"{}", "") is False
        assert verify_signature(APP_SECRET, b"{}", "sha256=") is False

    def test_wrong_prefix_rejected(self):
        assert verify_signature(APP_SECRET, b"{}", "md5=abc") is False

    def test_wrong_secret_rejected(self):
        body = b"{}"
        sig = "sha256=" + hmac.new(b"other", body, hashlib.sha256).hexdigest()
        assert verify_signature(APP_SECRET, body, sig) is False

    def test_empty_secret_never_valid(self):
        assert verify_signature("", b"{}", "sha256=abc") is False


# ── Webhook parsing ──────────────────────────────────────────────────


def _payload(*messages) -> dict:
    return {"entry": [{"changes": [{"value": {"messages": list(messages)}}]}]}


def _doc_message(**overrides) -> dict:
    msg = {
        "id": "wamid.HBgLMQ",
        "from": "911234567890",
        "timestamp": "1727300000",
        "type": "document",
        "document": {
            "id": "media-123",
            "mime_type": "application/pdf",
            "filename": "rental_agreement.pdf",
            "caption": "for tax filing",
        },
    }
    msg.update(overrides)
    return msg


class TestParseWebhook:
    def test_document_message_parsed(self):
        msgs = parse_webhook_event(_payload(_doc_message()), "911234567890")
        assert len(msgs) == 1
        assert msgs[0].msg_type == "document"
        assert msgs[0].media_id == "media-123"
        assert msgs[0].caption == "for tax filing"
        assert msgs[0].filename == "rental_agreement.pdf"
        assert msgs[0].message_id == "wamid.HBgLMQ"

    def test_text_message_parsed_with_reply_context(self):
        payload = _payload(
            {
                "id": "wamid.reply",
                "from": "911234567890",
                "type": "text",
                "text": {"body": "actually it's for rent, not tax"},
                "context": {"id": "wamid.original"},
            }
        )
        msgs = parse_webhook_event(payload, "911234567890")
        assert msgs[0].msg_type == "text"
        assert msgs[0].text == "actually it's for rent, not tax"
        assert msgs[0].reply_to_id == "wamid.original"

    def test_other_sender_dropped(self):
        payload = _payload(_doc_message(**{"from": "919999999999"}))
        assert parse_webhook_event(payload, "911234567890") == []

    def test_no_allow_list_accepts_anyone(self):
        payload = _payload(_doc_message(**{"from": "919999999999"}))
        assert len(parse_webhook_event(payload, None)) == 1

    def test_unknown_types_and_status_ignored(self):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {"id": "w1", "from": "911234567890", "type": "location"},
                                    {"id": "w2", "from": "911234567890", "type": "reaction"},
                                ],
                                "statuses": [{"id": "wamid.status", "status": "delivered"}],
                            }
                        }
                    ]
                }
            ]
        }
        assert parse_webhook_event(payload, "911234567890") == []

    def test_batched_messages_all_walked(self):
        payload = _payload(_doc_message(), _doc_message(id="wamid.2"))
        assert len(parse_webhook_event(payload, "911234567890")) == 2


# ── Message → Capture ────────────────────────────────────────────────


class TestCaptureBuilding:
    def test_text_message_becomes_capture(self):
        msg = WhatsAppMessage(message_id="m1", sender="s", msg_type="text", text="hello brain")
        cap = capture_from_message(msg)
        assert cap is not None
        assert cap.content == "hello brain"
        assert cap.source_type == "whatsapp"
        assert cap.sender_message_id == "m1"
        assert cap.metadata["wamid"] == "m1"

    def test_media_without_bytes_returns_none(self):
        msg = WhatsAppMessage(message_id="m2", sender="s", msg_type="document", media_id="x")
        assert capture_from_message(msg) is None

    def test_pdf_bytes_extracted(self):
        import fitz

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "RENT AGREEMENT between landlord and tenant")
        pdf_bytes = doc.tobytes()
        doc.close()

        text = extract_text_from_media(pdf_bytes, "application/pdf", "rent.pdf")
        assert "RENT AGREEMENT" in text

    def test_caption_used_when_image_has_no_text_layer(self):
        msg = WhatsAppMessage(
            message_id="m3",
            sender="s",
            msg_type="image",
            media_id="img",
            caption="passport scan for visa",
            mime_type="image/jpeg",
        )
        cap = capture_from_message(msg, raw_bytes=b"\x89PNG\r\nfakeimage")
        assert cap is not None
        assert "passport scan" in cap.content
        assert cap.caption == "passport scan for visa"

    def test_text_file_decoded(self):
        assert extract_text_from_media(b"# Note\nhello", "text/markdown", "note.md") == "# Note\nhello"


# ── Usage-context inference ──────────────────────────────────────────


class TestUsageContext:
    def test_caption_beats_heuristics(self):
        usage = infer_usage_context("random text", caption="for tax filing", filename="x.pdf", use_llm=False)
        assert usage.usage_context == "for tax filing"
        assert usage.inferred_by == "caption"
        assert "tax" in usage.purpose_tags
        assert usage.confidence >= 0.8

    def test_tags_from_content(self):
        assert "health" in tag_text("medical prescription from hospital")
        assert "travel" in tag_text("visa approval letter")
        assert tag_text("nothing relevant here") == ["other"]

    def test_expiry_dates_parsed(self):
        assert parse_expiry_date("expires 2027-03-01") is not None
        assert parse_expiry_date("renew by 12 March 2027") is not None
        assert parse_expiry_date("renew by 01/04/2027") is not None
        assert parse_expiry_date("a nice recipe for pasta") is None

    def test_filename_becomes_title(self):
        usage = infer_usage_context("body", caption=None, filename="rental_agreement.pdf", use_llm=False)
        assert usage.title == "rental agreement"

    def test_llm_failure_falls_back(self, monkeypatch):
        import anthropic

        class _FailingClient:
            def __init__(self, *args, **kwargs):
                class _Messages:
                    def create(self, *a, **k):
                        raise RuntimeError("api unavailable")

                self.messages = _Messages()

        monkeypatch.setattr(anthropic, "Anthropic", _FailingClient)
        monkeypatch.setattr(settings, "anthropic_api_key", "sk-invalid", raising=False)
        usage = infer_usage_context("salary payslip", caption="for finance", filename="pay.pdf")
        assert usage.usage_context == "for finance"
        assert usage.inferred_by == "caption"


# ── Encrypted blob store (TRD §7 encryption at rest) ────────────────


class TestBlobStore:
    def test_roundtrip_and_no_plaintext_on_disk(self, tmp_path):
        store = BlobStore(directory=tmp_path, key="unit-test-passphrase")
        secret = b"My Aadhaar number is 1234-5678-9012"
        rel = store.put(secret, doc_id="abc123", suffix=".pdf")

        on_disk = (tmp_path / "abc123.pdf").read_bytes()
        assert secret not in on_disk
        assert on_disk.startswith(b"gAAAA")  # Fernet ciphertext
        assert store.get(rel) == secret

    def test_key_resolution_sources(self, tmp_path):
        assert BlobStore(directory=tmp_path, key="a-passphrase").key_source == "env-passphrase"
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        assert BlobStore(directory=tmp_path, key=key).key_source == "env-fernet-key"

    def test_wrong_key_fails_loudly(self, tmp_path):
        store = BlobStore(directory=tmp_path, key="right-passphrase")
        rel = store.put(b"secret bytes", doc_id="doc1", suffix=".pdf")
        other = BlobStore(directory=tmp_path, key="wrong-passphrase")
        with pytest.raises(ValueError, match="wrong blob key"):
            other.get(rel)

    def test_missing_blob_raises(self, tmp_path):
        store = BlobStore(directory=tmp_path, key="p")
        with pytest.raises(FileNotFoundError):
            store.get("documents/nope.pdf")

    def test_generated_key_persists(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "blob_key", "", raising=False)
        store = BlobStore(directory=tmp_path, key="")
        assert store.key_source == "generated-file"
        key_file = tmp_path.parent / ".blob_key"
        assert key_file.exists()
        # second store reuses the same generated key
        again = BlobStore(directory=tmp_path, key="")
        assert again._fernet.encrypt(b"x") is not None
        assert store.get(store.put(b"y", doc_id="d2", suffix=".bin")) == b"y"
