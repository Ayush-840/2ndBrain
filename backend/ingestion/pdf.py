"""PDF ingestion adapter.

Uses PyMuPDF (fitz) for text extraction — fast, no system-level deps.
Returns one Capture per PDF file; page text is concatenated.
"""

from pathlib import Path

import fitz  # pymupdf

from backend.ingestion.base import Capture, IngestionAdapter


class PDFAdapter(IngestionAdapter):
    source_type = "pdf"

    def ingest(self, source: str) -> list[Capture]:
        """Ingest a single PDF or a directory of PDFs."""
        path = Path(source)

        if path.is_file() and path.suffix.lower() == ".pdf":
            return [self._parse_file(path)]

        if path.is_dir():
            captures: list[Capture] = []
            for pdf_file in sorted(path.rglob("*.pdf")):
                captures.append(self._parse_file(pdf_file))
            return captures

        raise FileNotFoundError(f"Source not found or not .pdf: {source}")

    def _parse_file(self, filepath: Path) -> Capture:
        doc = fitz.open(str(filepath))
        pages: list[str] = []
        for page in doc:
            pages.append(page.get_text())
        doc.close()

        full_text = "\n\n".join(pages).strip()
        metadata: dict = {
            "filename": filepath.name,
            "relative_path": str(filepath),
            "num_pages": len(pages),
        }

        return self._make_capture(
            content=full_text,
            source_path=str(filepath),
            metadata=metadata,
        )
