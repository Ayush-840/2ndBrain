"""LLM-based fact extraction using Claude tool calling.

Sends text chunks to Claude and asks it to extract:
  1. Entities (people, concepts, tools, papers, etc.)
  2. Relations between entities (works_on, uses, believes, etc.)
  3. Timestamped claims ("as of 2026-08-20, user believes X")

Uses Claude's tool-calling for structured output — no regex parsing.
The extracted data is returned as typed dicts that map directly to
the graph schema.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import anthropic

from backend.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ExtractedEntity:
    entity_id: str
    label: str
    entity_type: str  # "person", "concept", "tool", "paper", "organization", etc.


@dataclass
class ExtractedFact:
    subject: str  # entity_id
    predicate: str  # relationship label
    object_id: str | None = None  # another entity_id
    object_literal: str | None = None  # or a literal value
    valid_from: str | None = None
    valid_to: str | None = None
    confidence: float = 1.0


@dataclass
class ExtractionResult:
    entities: list[ExtractedEntity]
    facts: list[ExtractedFact]
    raw_response: str = ""


# ── Claude tool definitions ─────────────────────────────────────────

EXTRACTION_TOOLS = [
    {
        "name": "extract_entities",
        "description": (
            "Extract distinct entities mentioned in the text. "
            "Each entity should have a unique lowercase slug ID, a human-readable label, "
            "and a type (person, concept, tool, paper, organization, technique, etc.)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "entity_id": {
                                "type": "string",
                                "description": "Unique lowercase slug, e.g. 'transformer_architecture'",
                            },
                            "label": {
                                "type": "string",
                                "description": "Human-readable name",
                            },
                            "entity_type": {
                                "type": "string",
                                "description": "Type: person, concept, tool, paper, organization, technique, etc.",
                            },
                        },
                        "required": ["entity_id", "label", "entity_type"],
                    },
                    "description": "List of entities found in the text",
                },
            },
            "required": ["entities"],
        },
    },
    {
        "name": "extract_facts",
        "description": (
            "Extract factual relationships and claims from the text. "
            "Each fact connects a subject entity to an object (entity or literal) "
            "via a predicate. Include temporal qualifiers when the text specifies "
            "when something was true or when the author believes something."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "facts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "subject": {
                                "type": "string",
                                "description": "entity_id of the subject",
                            },
                            "predicate": {
                                "type": "string",
                                "description": (
                                    "Relationship label, e.g. 'works_on', 'uses', 'believes', "
                                    "'part_of', 'supersedes', 'authored_by'"
                                ),
                            },
                            "object_id": {
                                "type": "string",
                                "description": "entity_id of the object (if it's another entity)",
                            },
                            "object_literal": {
                                "type": "string",
                                "description": "Literal value of the object (if not an entity)",
                            },
                            "valid_from": {
                                "type": "string",
                                "description": "ISO8601 date when this fact started being true in the world",
                            },
                            "valid_to": {
                                "type": "string",
                                "description": "ISO8601 date when this fact stopped being true (null if still active)",
                            },
                            "confidence": {
                                "type": "number",
                                "description": "Confidence 0.0-1.0 that this fact is accurately extracted",
                            },
                        },
                        "required": ["subject", "predicate"],
                    },
                    "description": "List of facts/relationships extracted from the text",
                },
            },
            "required": ["facts"],
        },
    },
]

EXTRACTION_SYSTEM_PROMPT = """You are a knowledge extraction engine. Your job is to read text and extract structured entities and facts.

Rules:
1. Extract ALL meaningful entities — people, concepts, tools, techniques, papers, organizations.
2. Use lowercase slug IDs for entities (e.g., "bi_temporal_modeling", "claude_api").
3. Extract factual relationships with precise predicates.
4. When the text mentions a time period or date, include valid_from/valid_to on the fact.
5. When the author expresses a belief or opinion, use the predicate "believes" and note the recorded date.
6. Assign confidence based on how explicitly the text states the fact.
7. For contradictions (text says X is true, but also mentions Y replacing X), create separate facts and note which supersedes which.
8. Object must be either object_id (entity reference) or object_literal (string value), never both."""

# Current date context for the LLM
def _get_date_context() -> str:
    now = datetime.now(timezone.utc)
    return f"Today's date: {now.strftime('%Y-%m-%d')}"


class FactExtractor:
    """Extracts entities and facts from text using Claude tool calling."""

    def __init__(self, api_key: str | None = None):
        self._client = anthropic.Anthropic(
            api_key=api_key or settings.anthropic_api_key
        )
        self._model = settings.anthropic_model

    def extract(self, text: str, *, source_context: str = "") -> ExtractionResult:
        """Extract entities and facts from a text chunk.

        Args:
            text: The text to extract from.
            source_context: Optional context about where this text came from.

        Returns:
            ExtractionResult with entities, facts, and raw response.
        """
        if not text.strip():
            return ExtractionResult(entities=[], facts=[])

        system = EXTRACTION_SYSTEM_PROMPT + "\n\n" + _get_date_context()

        user_content = text
        if source_context:
            user_content = f"[Source: {source_context}]\n\n{text}"

        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system,
            tools=EXTRACTION_TOOLS,
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": user_content}],
        )

        return self._parse_response(response)

    def extract_batch(
        self,
        texts: list[str],
        *,
        source_contexts: list[str] | None = None,
    ) -> list[ExtractionResult]:
        """Extract from multiple texts sequentially.

        (Could be parallelized with async, but keeping it simple for v1.)
        """
        source_contexts = source_contexts or ["" for _ in texts]
        return [
            self.extract(text, source_context=ctx)
            for text, ctx in zip(texts, source_contexts)
        ]

    def _parse_response(self, response) -> ExtractionResult:
        """Parse Claude's tool-call response into ExtractionResult."""
        entities: list[ExtractedEntity] = []
        facts: list[ExtractedFact] = []
        raw_parts: list[str] = []

        for block in response.content:
            if block.type == "tool_use":
                raw_parts.append(json.dumps(block.input, indent=2))

                if block.name == "extract_entities":
                    for ent in block.input.get("entities", []):
                        entities.append(
                            ExtractedEntity(
                                entity_id=ent["entity_id"].lower().strip().replace(" ", "_"),
                                label=ent["label"],
                                entity_type=ent.get("entity_type", "concept"),
                            )
                        )

                elif block.name == "extract_facts":
                    for f in block.input.get("facts", []):
                        # Validate: exactly one of object_id or object_literal
                        obj_id = f.get("object_id")
                        obj_lit = f.get("object_literal")
                        if not obj_id and not obj_lit:
                            obj_lit = f.get("predicate", "unknown")

                        facts.append(
                            ExtractedFact(
                                subject=f["subject"].lower().strip().replace(" ", "_"),
                                predicate=f["predicate"],
                                object_id=obj_id.lower().strip().replace(" ", "_") if obj_id else None,
                                object_literal=obj_lit,
                                valid_from=f.get("valid_from"),
                                valid_to=f.get("valid_to"),
                                confidence=f.get("confidence", 0.8),
                            )
                        )

            elif block.type == "text":
                raw_parts.append(block.text)

        return ExtractionResult(
            entities=entities,
            facts=facts,
            raw_response="\n".join(raw_parts),
        )
