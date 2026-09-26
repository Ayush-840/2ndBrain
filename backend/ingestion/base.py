"""Abstract base class for ingestion adapters.

Every adapter takes a source (file path or URL) and returns a list of
raw Captures — the immutable episodic units that the rest of the pipeline
operates on.  Concrete adapters live in this package (markdown.py, pdf.py).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class Capture:
    """A single raw ingestion unit — immutable once created."""

    content: str
    source_path: str
    source_type: str  # "markdown", "pdf", "url", "whatsapp", etc.
    metadata: dict = field(default_factory=dict)
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    capture_id: str = field(default_factory=lambda: uuid4().hex)
    # Phase 6 — optional WhatsApp fields (ignored by the other adapters).
    caption: str | None = None
    sender_message_id: str | None = None


class IngestionAdapter(ABC):
    """Base interface that all ingestion adapters must implement."""

    source_type: str = "unknown"

    @abstractmethod
    def ingest(self, source: str) -> list[Capture]:
        """Ingest from `source` (file path or URL) and return Captures."""
        ...

    def _make_capture(
        self,
        content: str,
        source_path: str,
        metadata: dict | None = None,
    ) -> Capture:
        return Capture(
            content=content,
            source_path=source_path,
            source_type=self.source_type,
            metadata=metadata or {},
        )
