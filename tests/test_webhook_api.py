"""Phase 6/7 API tests: webhook receiver, Document nodes, documents API, security."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import backend.api.routes_documents as documents_routes
import backend.api.routes_ingest_whatsapp as webhook_routes
from backend.config import settings
from backend.ingestion.whatsapp import WhatsAppClient
from backend.main import app
from backend.memory.community import CommunityStore
from backend.memory.episodic import EpisodicStore
from backend.memory.graph import TemporalGraph
from backend.pipeline import Pipeline
from backend.retrieval.bm25 import BM25Index
from backend.security import security_problems, validate_security

APP_SECRET = "test-app-secret"
SENDER = "911234567890"
WEBHOOK = "/ingest/whatsapp/webhook"


def _make_pdf(text: str = "RENT AGREEMENT for the financial year") -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _sign(body: bytes, secret: str = APP_SECRET) -> dict:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {"X-Hub-Signature-256": f"sha256={digest}"}


def _post(client: TestClient, payload: dict, *, secret: str = APP_SECRET, raw: bytes | None = None):
    body = raw if raw is not None else json.dumps(payload).encode()
    return client.post(WEBHOOK, content=body, headers={"Content-Type": "application/json", **_sign(body, secret)})


def _doc_payload(message_id: str = "wamid.1", caption: str = "for tax filing") -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "id": message_id,
                                    "from": SENDER,
                                    "timestamp": "1727300000",
                                    "type": "document",
                                    "document": {
                                        "id": "media-1",
                                        "mime_type": "application/pdf",
                                        "filename": "rental_agreement.pdf",
                                        "caption": caption,
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Fresh pipeline + configured WhatsApp settings + stubbed Meta API."""
    for attr, value in {
        "whatsapp_access_token": "token",
        "whatsapp_phone_number_id": "555",
        "whatsapp_app_secret": APP_SECRET,
        "whatsapp_verify_token": "verify-me",
        "whatsapp_allowed_sender": SENDER,
        "whatsapp_allow_unsigned": False,
        "processed_ids_path": tmp_path / "ledger.json",
        "blob_dir": tmp_path / "documents",
        "blob_key": "test-passphrase",
        "auth_enabled": True,
        "auth_password_hash": "sha256:not-the-default",
        "anthropic_api_key": "",
        "allow_insecure": False,
    }.items():
        monkeypatch.setattr(settings, attr, value, raising=False)

    pipeline = Pipeline(
        episodic_store=EpisodicStore(persist_dir=str(tmp_path / "chroma")),
        bm25_index=BM25Index(),
        graph=TemporalGraph(),
        community=CommunityStore(),
    )
    import backend.api.routes_query as query_routes

    monkeypatch.setattr(webhook_routes, "get_pipeline", lambda: pipeline)
    monkeypatch.setattr(documents_routes, "get_pipeline", lambda: pipeline)
    monkeypatch.setattr(query_routes, "get_pipeline", lambda: pipeline)

    webhook_routes._seen_docs.clear()
    webhook_routes._pending.clear()
    webhook_routes._last_doc_by_sender.clear()

    sent: list[dict] = []
    pdf = _make_pdf()
    monkeypatch.setattr(
        WhatsAppClient, "download_media", lambda self, media_id: pdf, raising=False
    )
    monkeypatch.setattr(
        WhatsAppClient,
        "send_text",
        lambda self, to, body: sent.append({"to": to, "body": body}) or True,
        raising=False,
    )

    return SimpleNamespace(pipeline=pipeline, sent=sent, tmp=tmp_path)


# ── Webhook handshake + signature gate ───────────────────────────────


class TestWebhookSecurity:
    def test_get_handshake_echoes_challenge(self, env):
        with TestClient(app) as client:
            resp = client.get(
                WEBHOOK,
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": "verify-me",
                    "hub.challenge": "1234567890",
                },
            )
        assert resp.status_code == 200
        assert resp.text == "1234567890"
        assert "text/plain" in resp.headers["content-type"]

    def test_get_handshake_wrong_token_403(self, env):
        with TestClient(app) as client:
            resp = client.get(
                WEBHOOK,
                params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "1"},
            )
        assert resp.status_code == 403

    def test_post_bad_signature_401(self, env):
        with TestClient(app) as client:
            resp = _post(client, _doc_payload(), secret="wrong-secret")
        assert resp.status_code == 401

    def test_post_missing_signature_401(self, env):
        body = json.dumps(_doc_payload()).encode()
        with TestClient(app) as client:
            resp = client.post(WEBHOOK, content=body, headers={"Content-Type": "application/json"})
        assert resp.status_code == 401

    def test_fail_closed_without_app_secret(self, env, monkeypatch):
        # No lifespan here: startup itself would refuse this config (see
        # TestSecurityGate) — this asserts the route refuses it too.
        monkeypatch.setattr(settings, "whatsapp_app_secret", "")
        body = json.dumps(_doc_payload()).encode()
        client = TestClient(app)
        resp = client.post(
            WEBHOOK,
            content=body,
            headers={"Content-Type": "application/json", **_sign(body)},
        )
        assert resp.status_code == 401

    def test_unsigned_allowed_only_when_explicit(self, env, monkeypatch):
        monkeypatch.setattr(settings, "whatsapp_app_secret", "")
        monkeypatch.setattr(settings, "whatsapp_allow_unsigned", True)
        body = json.dumps(_doc_payload(message_id="wamid.unsigned")).encode()
        client = TestClient(app)
        resp = client.post(WEBHOOK, content=body, headers={"Content-Type": "application/json"})
        assert resp.status_code == 200

    def test_invalid_json_400(self, env):
        with TestClient(app) as client:
            resp = _post(client, None, raw=b"not-json")
        assert resp.status_code == 400


# ── End-to-end capture ───────────────────────────────────────────────


class TestCaptureFlow:
    def test_document_reaches_store_and_replies(self, env):
        with TestClient(app) as client:
            resp = _post(client, _doc_payload())

        assert resp.status_code == 200
        assert resp.json() == {"status": "received", "accepted": 1}

        docs = env.pipeline.graph.list_documents()
        assert len(docs) == 1
        doc = docs[0]
        assert doc["source_channel"] == "whatsapp"
        assert doc["source_message_id"] == "wamid.1"
        assert doc["episodic_ref"]
        assert "tax" in doc["purpose_tags"]
        assert doc["usage_context"] == "for tax filing"  # caption wins
        assert doc["inferred_by"] in ("caption", "llm")

        assert env.pipeline.store.count >= 1

        # Original bytes encrypted at rest, not written in plaintext
        blob = env.tmp / "documents" / f"{doc['episodic_ref']}.pdf"
        assert blob.exists()
        assert b"RENT AGREEMENT" not in blob.read_bytes()

        # Confirmation reply
        assert len(env.sent) == 1
        assert env.sent[0]["to"] == SENDER
        assert "rental agreement" in env.sent[0]["body"].lower()
        assert "tax" in env.sent[0]["body"].lower()

    def test_duplicate_delivery_is_ignored(self, env):
        with TestClient(app) as client:
            first = _post(client, _doc_payload(message_id="wamid.dup"))
            second = _post(client, _doc_payload(message_id="wamid.dup"))

        assert first.json()["accepted"] == 1
        assert second.json()["accepted"] == 0
        assert len(env.pipeline.graph.list_documents()) == 1

    def test_ledger_survives_restart(self, env):
        with TestClient(app) as client:
            _post(client, _doc_payload(message_id="wamid.persist"))

        ledger = json.loads((env.tmp / "ledger.json").read_text())
        assert "wamid.persist" in ledger["processed"]
        assert any(ledger["docs"].values())

        # Simulate a restart: module caches cleared, ledger reloaded from disk
        webhook_routes._seen_docs.clear()
        webhook_routes._pending.clear()
        with TestClient(app) as client:
            again = _post(client, _doc_payload(message_id="wamid.persist"))
        assert again.json()["accepted"] == 0
        assert len(env.pipeline.graph.list_documents()) == 1

    def test_wrong_sender_ignored(self, env):
        payload = _doc_payload()
        payload["entry"][0]["changes"][0]["value"]["messages"][0]["from"] = "910000000000"
        with TestClient(app) as client:
            resp = _post(client, payload)
        assert resp.json()["accepted"] == 0
        assert env.pipeline.graph.list_documents() == []


class TestCorrectionFlow:
    def test_reply_corrects_purpose_bi_temporally(self, env):
        with TestClient(app) as client:
            _post(client, _doc_payload(message_id="wamid.orig"))
            reply = {
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "messages": [
                                        {
                                            "id": "wamid.reply",
                                            "from": SENDER,
                                            "type": "text",
                                            "text": {"body": "actually this is for my rent, not tax"},
                                            "context": {"id": "wamid.orig"},
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            }
            resp = _post(client, reply)

        assert resp.json()["accepted"] == 1

        docs = env.pipeline.graph.list_documents()
        assert len(docs) == 1  # old version is superseded, not listed
        assert docs[0]["usage_context"] == "actually this is for my rent, not tax"
        assert docs[0]["inferred_by"] == "user"
        assert "finance" in docs[0]["purpose_tags"] or "legal" in docs[0]["purpose_tags"]

        history = env.pipeline.graph.list_documents(include_superseded=True)
        assert len(history) == 2
        old = next(d for d in history if d["document_id"] != docs[0]["document_id"])
        assert old["superseded_by"] == docs[0]["document_id"]
        assert old["valid_to"] is not None

        # Confirmation of the correction was sent
        assert any("Updated" in m["body"] for m in env.sent)

    def test_text_without_target_document_is_ignored(self, env):
        with TestClient(app) as client:
            resp = _post(
                client,
                {
                    "entry": [
                        {
                            "changes": [
                                {
                                    "value": {
                                        "messages": [
                                            {
                                                "id": "wamid.stray",
                                                "from": SENDER,
                                                "type": "text",
                                                "text": {"body": "just chatting"},
                                            }
                                        ]
                                    }
                                }
                            ]
                        }
                    ]
                },
            )
        assert resp.status_code == 200
        assert env.pipeline.graph.list_documents() == []


# ── Documents API ────────────────────────────────────────────────────


@pytest.fixture
def docs_env(env):
    """Seed one document through the real pipeline."""
    from backend.ingestion.base import Capture

    capture = Capture(
        content="VISA APPROVAL for business travel",
        source_path="whatsapp/wamid.seed",
        source_type="whatsapp",
        caption="visa document, renew before expiry",
        sender_message_id="wamid.seed",
        metadata={"filename": "visa_approval.pdf"},
    )
    result = env.pipeline.ingest_document(
        capture,
        filename="visa_approval.pdf",
        mime_type="application/pdf",
        blob_bytes=_make_pdf("VISA APPROVAL"),
        source_channel="whatsapp",
        use_llm=False,
        # force an expiring document
    )
    # Set a near expiry for status tests
    from datetime import datetime, timedelta

    env.pipeline.graph._graph.nodes[result["doc_id"]]["valid_until"] = (
        datetime.now(UTC) + timedelta(days=5)
    ).isoformat()
    env.doc_id = result["doc_id"]
    return env


class TestDocumentsAPI:
    def test_list_and_tags(self, docs_env):
        with TestClient(app) as client:
            resp = client.get("/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["documents"][0]["document_id"] == docs_env.doc_id
        assert data["documents"][0]["status"] in ("red", "amber", "green")
        assert data["tags"]

    def test_filter_by_purpose_tag(self, docs_env):
        doc = docs_env.pipeline.graph.get_document(docs_env.doc_id)
        tag = doc["purpose_tags"][0]
        with TestClient(app) as client:
            resp = client.get("/documents", params={"tag": tag})
            miss = client.get("/documents", params={"tag": "no-such-tag"})
        assert resp.json()["total"] == 1
        assert miss.json()["total"] == 0

    def test_expiring_endpoint(self, docs_env):
        with TestClient(app) as client:
            resp = client.get("/documents/expiring", params={"days": 30})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["documents"][0]["days_left"] <= 30

    def test_status_endpoint(self, docs_env):
        with TestClient(app) as client:
            resp = client.get("/documents/status")
        data = resp.json()
        assert data["whatsapp"]["configured"] is True
        assert data["whatsapp"]["ready"] is True
        assert data["whatsapp"]["last_capture"]

    def test_correct_endpoint_supersedes(self, docs_env):
        with TestClient(app) as client:
            resp = client.post(
                f"/documents/{docs_env.doc_id}/correct",
                json={"usage_context": "for my visa renewal in March"},
            )
        assert resp.status_code == 200
        new_doc = resp.json()["document"]
        assert new_doc["document_id"] != docs_env.doc_id
        assert new_doc["usage_context"] == "for my visa renewal in March"
        # old one still exists in history
        assert docs_env.pipeline.graph.get_document(docs_env.doc_id)["superseded_by"]

    def test_correct_unknown_document_404(self, docs_env):
        with TestClient(app) as client:
            resp = client.post("/documents/doc_nope/correct", json={"usage_context": "x"})
        assert resp.status_code == 404

    def test_get_document_and_download(self, docs_env):
        with TestClient(app) as client:
            got = client.get(f"/documents/{docs_env.doc_id}")
            file_resp = client.get(f"/documents/{docs_env.doc_id}/file")
            missing = client.get("/documents/doc_missing/file")
        assert got.status_code == 200
        assert file_resp.status_code == 200
        assert file_resp.content.startswith(b"%PDF")  # decrypted back to the original
        import fitz

        doc = fitz.open(stream=file_resp.content, filetype="pdf")
        assert "VISA APPROVAL" in doc[0].get_text()
        doc.close()
        assert missing.status_code == 404


# ── Purpose-aware retrieval (Phase 7) ────────────────────────────────


class TestPurposeAwareQuery:
    def test_document_intent_boosted(self, docs_env):
        with TestClient(app) as client:
            resp = client.post("/query", json={"query": "which document do I need for my visa renewal"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"], "expected at least one result"
        assert data["results"][0]["source"] == "document+purpose"
        assert "visa" in data["results"][0]["metadata"]["usage_context"].lower() or \
               "visa" in data["results"][0]["metadata"]["title"].lower()
        assert "document" in data["sources_used"]

    def test_ordinary_query_not_boosted(self, docs_env):
        with TestClient(app) as client:
            resp = client.post("/query", json={"query": "what is bi-temporal modeling"})
        assert resp.status_code == 200
        sources = resp.json()["sources_used"]
        assert "document" not in sources


# ── Security gate (PRD 6.2) ──────────────────────────────────────────


class TestSecurityGate:
    def test_missing_app_secret_blocks_startup(self, monkeypatch):
        monkeypatch.setattr(settings, "whatsapp_access_token", "t")
        monkeypatch.setattr(settings, "whatsapp_phone_number_id", "p")
        monkeypatch.setattr(settings, "whatsapp_app_secret", "")
        monkeypatch.setattr(settings, "allow_insecure", False)
        problems = security_problems()
        assert any("APP_SECRET" in p for p in problems)
        with pytest.raises(RuntimeError, match="security requirements"):
            validate_security()

    def test_default_password_blocks_startup(self, monkeypatch):
        for attr, value in {
            "whatsapp_access_token": "t",
            "whatsapp_phone_number_id": "p",
            "whatsapp_app_secret": "s",
            "whatsapp_allowed_sender": "91",
            "whatsapp_verify_token": "v",
            "auth_enabled": True,
            "auth_password": "changeme",
            "auth_password_hash": "",
            "allow_insecure": False,
        }.items():
            monkeypatch.setattr(settings, attr, value, raising=False)
        with pytest.raises(RuntimeError, match="default value"):
            validate_security()

    def test_complete_configuration_passes(self, monkeypatch):
        for attr, value in {
            "whatsapp_access_token": "t",
            "whatsapp_phone_number_id": "p",
            "whatsapp_app_secret": "s",
            "whatsapp_allowed_sender": "91",
            "whatsapp_verify_token": "v",
            "auth_enabled": True,
            "auth_password_hash": "sha256:strong",
            "allow_insecure": False,
        }.items():
            monkeypatch.setattr(settings, attr, value, raising=False)
        assert security_problems() == []
        validate_security()  # must not raise

    def test_disabled_whatsapp_is_clean(self, monkeypatch):
        monkeypatch.setattr(settings, "whatsapp_access_token", "")
        monkeypatch.setattr(settings, "whatsapp_phone_number_id", "")
        monkeypatch.setattr(settings, "allow_insecure", False)
        assert security_problems() == []

    def test_allow_insecure_bypasses(self, monkeypatch):
        monkeypatch.setattr(settings, "whatsapp_access_token", "t")
        monkeypatch.setattr(settings, "whatsapp_phone_number_id", "p")
        monkeypatch.setattr(settings, "whatsapp_app_secret", "")
        monkeypatch.setattr(settings, "allow_insecure", True)
        validate_security()  # must not raise
