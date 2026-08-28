"""Markdown / Obsidian vault ingestion adapter.

Handles nested vaults, YAML frontmatter, and tags/aliases — the standard
Obsidian layout.  Returns one Capture per .md file.
"""

from pathlib import Path

from datetime import date, datetime

import frontmatter

from backend.ingestion.base import Capture, IngestionAdapter


class MarkdownAdapter(IngestionAdapter):
    source_type = "markdown"

    def ingest(self, source: str) -> list[Capture]:
        """Ingest a single .md file or an entire vault directory."""
        path = Path(source)

        if path.is_file() and path.suffix == ".md":
            return [self._parse_file(path)]

        if path.is_dir():
            captures: list[Capture] = []
            for md_file in sorted(path.rglob("*.md")):
                captures.append(self._parse_file(md_file))
            return captures

        raise FileNotFoundError(f"Source not found or not .md: {source}")

    def _parse_file(self, filepath: Path) -> Capture:
        raw = filepath.read_text(encoding="utf-8")
        post = frontmatter.loads(raw)

        metadata: dict = {
            "filename": filepath.name,
            "relative_path": str(filepath),
        }
        # Carry Obsidian frontmatter fields into metadata
        # ChromaDB only accepts str/int/float/bool/list/None, so convert dates
        if post.metadata:
            for key in ("tags", "aliases", "title", "created", "updated"):
                if key in post.metadata:
                    val = post.metadata[key]
                    if isinstance(val, (date, datetime)):
                        val = val.isoformat()
                    metadata[key] = val

        return self._make_capture(
            content=post.content.strip(),
            source_path=str(filepath),
            metadata=metadata,
        )
