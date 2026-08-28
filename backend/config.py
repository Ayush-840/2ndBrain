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


settings = Settings()
