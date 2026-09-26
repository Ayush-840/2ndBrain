"""Privacy-tiered LLM routing (06-additional-features §3).

Route by *content sensitivity*, not an all-or-nothing deployment choice:

    Identity / Medical / Financial  ──► local model (never leaves the machine)
    everything else                 ──► cloud model (higher quality)

Sensitivity is decided from the evidence that will actually be sent to the
model: purpose tags on retrieved documents, encrypted profile fields, and the
question itself. If the preferred tier is not configured, the decision
records an explicit fallback so the caller (and the audit log) can see it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.config import settings

# Tokens that mark a question as touching an encrypted profile field even
# when no document is retrieved (e.g. "what's my aadhaar number").
_FIELD_ALIASES = {
    "govt_id_number": ("govt id", "government id", "id number"),
    "passport_number": ("passport",),
    "pan_number": ("pan", "pan card"),
    "aadhaar": ("aadhaar", "aadhar", "uidai"),
    "bank_account": ("bank account", "account number", "ifsc"),
    "education_loan_amount": ("loan amount", "education loan", "emi"),
}


class LLMUnavailableError(RuntimeError):
    """No LLM tier (cloud or local) is configured."""


@dataclass
class RouteDecision:
    provider: str  # "cloud" | "local"
    model: str
    reason: str  # why this tier was chosen (incl. fallback)
    sensitive: bool  # whether sensitive evidence was found
    fallback_from: str | None = None  # preferred tier if it was unavailable

    def as_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "reason": self.reason,
            "sensitive": self.sensitive,
            "fallback_from": self.fallback_from,
        }


def _result_is_sensitive(metadata: dict, sensitive: set[str]) -> bool:
    """True if a retrieved chunk carries sensitive evidence."""
    tag_sets = (
        metadata.get("purpose_tags") or [],
        metadata.get("tags") or [],
        [metadata.get("usage_context") or ""],
        [metadata.get("category") or ""],
    )
    for group in tag_sets:
        for tag in group:
            if str(tag).strip().lower() in sensitive:
                return True
    # Encrypted profile field hits: the profile routes put the field name
    # in metadata["field"] and mark the fact as encrypted.
    field = str(metadata.get("field", "")).strip().lower()
    if field and field in settings.sensitive_fields:
        return True
    if metadata.get("encrypted") or metadata.get("sensitive"):
        return True
    return False


def _query_is_sensitive(question: str) -> bool:
    q = question.lower()
    if any(tok in q for toks in _FIELD_ALIASES.values() for tok in toks):
        return True
    return any(f in q for f in settings.sensitive_fields)


def route_llm(question: str, results: list) -> RouteDecision:
    """Pick a model tier for this question + its retrieved evidence.

    Args:
        question: the user's question.
        results: SearchResult objects that will be sent as context.

    Raises:
        LLMUnavailableError: neither tier is configured.
    """
    sensitive = set(settings.sensitive_category_set)
    evidence_sensitive = any(
        _result_is_sensitive(getattr(r, "metadata", {}) or {}, sensitive) for r in results
    )
    is_sensitive = evidence_sensitive or _query_is_sensitive(question)

    preferred = "local" if is_sensitive else "cloud"
    fallback_from = None

    available = {"cloud": settings.cloud_llm_ready, "local": settings.local_llm_ready}
    if not any(available.values()):
        raise LLMUnavailableError(
            "no LLM configured: set BRAIN_ANTHROPIC_API_KEY (cloud) or "
            "BRAIN_LOCAL_LLM_BASE_URL (local)"
        )

    if available[preferred]:
        provider = preferred
    else:
        provider = "local" if preferred == "cloud" else "cloud"
        fallback_from = preferred

    reason = (
        "sensitive evidence → local model (data stays on this machine)"
        if is_sensitive and provider == "local" and not fallback_from
        else "non-sensitive → cloud model"
        if provider == "cloud" and not fallback_from
        else f"preferred tier '{preferred}' unavailable → fell back to '{provider}'"
    )

    return RouteDecision(
        provider=provider,
        model=settings.local_llm_model if provider == "local" else settings.anthropic_model,
        reason=reason,
        sensitive=is_sensitive,
        fallback_from=fallback_from,
    )
