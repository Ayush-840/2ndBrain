"""Usage-context inference — the "why did I save this?" field.

A payslip, a visa PDF and a recipe are all "documents", but they are
retrieved differently depending on *intended use*, not semantic content.
This module fills the one slot the old system didn't have:

    title          — human-readable name (filename or caption-derived)
    usage_context  — one or two sentences: what this is for and when it matters
    purpose_tags   — small controlled vocabulary (tax, finance, health, ...)
    valid_until    — optional expiry/renewal/deadline date (ISO8601)

Priority of signals, strongest first:
    1. Claude (if BRAIN_ANTHROPIC_API_KEY is set) — reads caption + content
    2. The user's own caption — their words beat any guess
    3. Heuristic keyword matching over filename + content

Every result is human-correctable in one WhatsApp reply or one click in
the UI; corrections supersede rather than overwrite (see memory/graph.py).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from backend.config import settings

logger = logging.getLogger(__name__)

# Small fixed taxonomy — the same tags the UI filter chips use.
PURPOSE_TAXONOMY: dict[str, tuple[str, ...]] = {
    "tax": ("tax", "itr", "filing", "form 16", "1099", "gst", "return", "deduction"),
    "finance": (
        "salary", "payslip", "invoice", "bank", "statement", "loan", "rent",
        "receipt", "payment", "insurance", "investment", "mutual fund", "pf ",
        "offer letter", "refund",
    ),
    "health": (
        "medical", "health", "prescription", "vaccine", "hospital", "doctor",
        "dental", "lab report", "insurance card", "therapy", "scan",
    ),
    "travel": ("visa", "passport", "boarding", "flight", "itinerary", "hotel", "ticket", "travel"),
    "education": ("degree", "transcript", "certificate", "marksheet", "semester", "course", "enrollment"),
    "identity": ("aadhaar", "pan card", "license", "driving licence", "birth certificate", "ssn", "id card"),
    "legal": ("agreement", "contract", "lease", "terms", "affidavit", "notary", "petition"),
    "admin": ("renewal", "registration", "application", "form", "receipt", "policy", "utility", "bill"),
}

DEFAULT_TAGS = ["other"]

# "expires 2027-03-01", "renew by 12 March 2027", "valid until 01/04/2027"
_DATE_WORDS = r"(?:expire[sd]?|expiry|renew(?:al)?|due|valid\s+until|before|by|deadline)"
_MONTHS = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)

_DATE_PATTERNS = [
    re.compile(rf"{_DATE_WORDS}\D{{0,20}}?(\d{{4}}-\d{{2}}-\d{{2}})", re.IGNORECASE),
    re.compile(rf"{_DATE_WORDS}\D{{0,20}}?(\d{{1,2}}\s+{_MONTHS}\s+\d{{4}})", re.IGNORECASE),
    re.compile(rf"{_DATE_WORDS}\D{{0,20}}?(\d{{1,2}}/\d{{1,2}}/\d{{4}})", re.IGNORECASE),
    # bare ISO date in a caption that already smells like a deadline
    re.compile(rf"(?:{_DATE_WORDS}).{{0,40}}?(\d{{4}}-\d{{2}}-\d{{2}})", re.IGNORECASE),
]


@dataclass
class UsageContext:
    """The answer to "what is this document for?" """

    title: str
    usage_context: str
    purpose_tags: list[str] = field(default_factory=lambda: list(DEFAULT_TAGS))
    valid_until: str | None = None
    inferred_by: str = "heuristic"  # "llm" | "caption" | "heuristic"
    confidence: float = 0.5

    @property
    def is_empty(self) -> bool:
        return not self.usage_context.strip()


def parse_expiry_date(text: str) -> str | None:
    """Find an expiry/renewal/deadline date in free text. Returns ISO or None."""
    if not text:
        return None
    for pattern in _DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        raw = match.group(1).strip()
        for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%d/%m/%Y"):
            try:
                dt = datetime.strptime(raw.title() if fmt != "%Y-%m-%d" else raw, fmt)  # noqa: DTZ007
                return dt.replace(tzinfo=UTC).isoformat()
            except ValueError:
                continue
    return None


def tag_text(text: str) -> list[str]:
    """Map free text onto the controlled purpose vocabulary."""
    lowered = text.lower()
    hits = [tag for tag, keywords in PURPOSE_TAXONOMY.items() if any(k in lowered for k in keywords)]
    # Deduplicate while preserving order, drop near-synonym overlaps
    seen: list[str] = []
    for tag in hits:
        if tag not in seen:
            seen.append(tag)
    return seen or list(DEFAULT_TAGS)


def _title_from(filename: str | None, content: str, caption: str | None) -> str:
    if filename:
        stem = filename.rsplit("/", 1)[-1]
        stem = stem.rsplit(".", 1)[0] if "." in stem else stem
        if stem:
            return stem.replace("_", " ").replace("-", " ").strip()
    if caption:
        return caption.strip()[:60]
    for line in content.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:60]
    return "Untitled document"


def _heuristic(
    content: str,
    *,
    caption: str | None,
    filename: str | None,
) -> UsageContext:
    """No LLM? Fall back to the caption (the user's own words) + keywords."""
    title = _title_from(filename, content, caption)
    searchable = " ".join(filter(None, [caption, filename, content[:1500]]))
    tags = tag_text(searchable)
    valid_until = parse_expiry_date(searchable)

    if caption:
        usage_context = caption.strip()
        inferred_by, confidence = "caption", 0.8
    else:
        first_line = next((ln.strip() for ln in content.splitlines() if ln.strip()), "")
        usage_context = first_line[:200] if first_line else ""
        inferred_by, confidence = "heuristic", 0.4

    return UsageContext(
        title=title,
        usage_context=usage_context,
        purpose_tags=tags,
        valid_until=valid_until,
        inferred_by=inferred_by,
        confidence=confidence,
    )


PURPOSE_TOOL = {
    "name": "record_document_purpose",
    "description": (
        "Record what a captured document is FOR — its purpose, not its raw content. "
        "This is what the owner will search by months later ('the file I need for taxes')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Short human-readable name for the document",
            },
            "usage_context": {
                "type": "string",
                "description": (
                    "1-2 sentences: what this document is for and when it will be needed again. "
                    "Write it as if telling the owner later. Empty string if genuinely unclear."
                ),
            },
            "purpose_tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "0-3 tags from: tax, finance, health, travel, education, identity, legal, admin, other"
                ),
            },
            "valid_until": {
                "type": ["string", "null"],
                "description": "ISO8601 date (YYYY-MM-DD) if the document expires or needs renewal, else null",
            },
            "confidence": {
                "type": "number",
                "description": "0.0-1.0 confidence in this purpose guess",
            },
        },
        "required": ["title", "usage_context", "purpose_tags", "valid_until"],
    },
}

_PURPOSE_SYSTEM = """You infer the PURPOSE of a personal document its owner saved.

You are given the filename (if any), a caption the owner typed when sending it,
and the document's own text. Decide what it is FOR and when it will matter again.

Rules:
1. The owner's caption is the strongest signal — if they wrote "for tax filing", use that.
2. usage_context is 1-2 plain sentences about intended use, never a summary of content.
3. purpose_tags come only from: tax, finance, health, travel, education, identity, legal, admin, other.
4. valid_until only when a real expiry/renewal/deadline exists (parse it to YYYY-MM-DD), else null.
5. If nothing indicates purpose, return usage_context="" and confidence<=0.3. Never invent one."""


def _llm_usage_context(
    content: str,
    *,
    caption: str | None,
    filename: str | None,
) -> UsageContext | None:
    """Ask Claude for the purpose. Returns None on any failure (caller falls back)."""
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        parts = []
        if filename:
            parts.append(f"[Filename: {filename}]")
        if caption:
            parts.append(f"[Owner's caption: {caption}]")
        parts.append(content[:6000])

        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1024,
            system=_PURPOSE_SYSTEM,
            tools=[PURPOSE_TOOL],
            tool_choice={"type": "tool", "name": "record_document_purpose"},
            messages=[{"role": "user", "content": "\n\n".join(parts)}],
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == "record_document_purpose":
                data = block.input
                tags = [str(t).lower().strip() for t in data.get("purpose_tags", []) if str(t).strip()]
                tags = [t for t in tags if t in PURPOSE_TAXONOMY] or list(DEFAULT_TAGS)
                valid_until = data.get("valid_until")
                return UsageContext(
                    title=str(data.get("title") or _title_from(filename, content, caption)),
                    usage_context=str(data.get("usage_context") or "").strip(),
                    purpose_tags=tags[:3],
                    valid_until=f"{valid_until}T00:00:00+00:00" if valid_until else None,
                    inferred_by="llm",
                    confidence=float(data.get("confidence", 0.85)),
                )
    except Exception as exc:  # noqa: BLE001 — never let purpose inference break ingestion
        logger.warning("LLM purpose inference failed, using fallback: %s", exc)
    return None


def infer_usage_context(
    content: str,
    *,
    caption: str | None = None,
    filename: str | None = None,
    use_llm: bool = True,
) -> UsageContext:
    """Infer what a document is for.

    Order: Claude → the owner's caption → keyword heuristics. Never raises.
    """
    if use_llm:
        result = _llm_usage_context(content, caption=caption, filename=filename)
        if result is not None:
            # An LLM that found nothing still beats nothing only if we have no caption
            if result.is_empty and caption:
                pass  # fall through to the caption path
            else:
                return result
    return _heuristic(content, caption=caption, filename=filename)
