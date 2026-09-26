"""Centralized configuration for the second-brain backend.

Uses pydantic-settings so all config is driven by environment variables
(or a .env file). This keeps secrets out of code and makes the project
easy to deploy differently later.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BRAIN_", env_file=".env", extra="ignore")

    # --- Paths ---
    data_dir: Path = Path("data")
    chroma_dir: Path = Path("data/chroma")
    vault_dir: Path = Path("data/sample_vault")
    # Durable knowledge graph (JSON). Saved on shutdown / after mutations.
    graph_path: Path = Path("data/graph.json")

    # --- Embedding model ---
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # --- Chunking ---
    chunk_size: int = 512  # characters
    chunk_overlap: int = 64  # characters

    # --- Retrieval ---
    top_k: int = 10
    bm25_weight: float = 0.3
    dense_weight: float = 0.5
    graph_weight: float = 0.2
    graph_hops: int = 2

    # --- LLM ---
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # --- ChromaDB ---
    chroma_collection: str = "episodic_memory"

    # --- Auth ---
    auth_enabled: bool = False
    auth_username: str = "admin"
    auth_password: str = "changeme"
    # Optional: pre-hashed password (bcrypt/sha256). If set, auth_password is ignored.
    auth_password_hash: str = ""

    # --- WhatsApp Cloud API (Phase 6) ---
    # All optional: the app boots fine without them (WhatsApp stays disabled).
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_allowed_sender: str = ""
    whatsapp_api_version: str = "v21.0"
    # Dev-only escape hatch: accept webhooks without a signature check.
    # Never enable this where the endpoint is publicly reachable.
    whatsapp_allow_unsigned: bool = False

    # --- Documents (Phase 6/7) ---
    document_expiry_warning_days: int = 30
    # Dedupe ledger for webhook deliveries (wamid → processed doc).
    processed_ids_path: Path = Path("data/whatsapp_processed_ids.json")

    # --- Encrypted document blob store (Phase 6.2) ---
    blob_dir: Path = Path("data/documents")
    # Fernet key or passphrase. Empty → a local key file is generated once
    # (data/.blob_key, mode 0600) so documents are still encrypted at rest.
    blob_key: str = ""

    # --- Safety gate ---
    # Explicit opt-out for the launch-blocking security checks in
    # backend/security.py. Only for local experiments with no real data.
    allow_insecure: bool = False

    # --- Personal profile (Phase 8: 06/07/08 feature extensions) ---
    # Comma-separated field names encrypted at the application boundary
    # before they touch the graph (research paper §7.2 / extensions §4).
    sensitive_profile_fields: str = (
        "govt_id_number,passport_number,pan_number,aadhaar,"
        "bank_account,education_loan_amount"
    )
    # Append-only audit log (extensions §4 "full access audit log").
    audit_log_path: Path = Path("data/audit.log.jsonl")
    # Persistent contradiction review queue (TRD §3 contradiction_flags).
    review_queue_path: Path = Path("data/contradictions.json")
    # Default horizon for the unified reminder feed.
    reminder_window_days: int = 30

    @property
    def sensitive_fields(self) -> set[str]:
        """Normalized set of profile fields that get field-level encryption."""
        return {f.strip().lower() for f in self.sensitive_profile_fields.split(",") if f.strip()}

    @property
    def whatsapp_enabled(self) -> bool:
        """True when the minimum WhatsApp credentials are present."""
        return bool(self.whatsapp_access_token and self.whatsapp_phone_number_id)

    @property
    def whatsapp_ready(self) -> bool:
        """True when the webhook can be safely used (signature + allow-list)."""
        return self.whatsapp_enabled and bool(
            self.whatsapp_app_secret and self.whatsapp_allowed_sender and self.whatsapp_verify_token
        )


settings = Settings()
