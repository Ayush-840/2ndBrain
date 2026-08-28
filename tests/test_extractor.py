"""Tests for the Claude-based fact extractor.

Uses mocked Claude responses to test parsing logic without actual API calls.
"""

import json
from unittest.mock import MagicMock, patch

from backend.enrichment.extractor import (
    ExtractionResult,
    ExtractedEntity,
    ExtractedFact,
    FactExtractor,
)


def _mock_tool_response(tool_name: str, tool_input: dict) -> MagicMock:
    """Create a mock Claude API response with a single tool call."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.input = tool_input

    response = MagicMock()
    response.content = [block]
    return response


def _mock_multi_tool_response(tool_calls: list[tuple[str, dict]]) -> MagicMock:
    """Create a mock response with multiple tool calls."""
    blocks = []
    for name, inp in tool_calls:
        block = MagicMock()
        block.type = "tool_use"
        block.name = name
        block.input = inp
        blocks.append(block)

    response = MagicMock()
    response.content = blocks
    return response


class TestFactExtractor:
    def setup_method(self):
        self.extractor = FactExtractor(api_key="test-key")

    @patch("anthropic.Anthropic")
    def test_extract_entities(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_client.messages.create.return_value = _mock_tool_response(
            "extract_entities",
            {
                "entities": [
                    {"entity_id": "claude", "label": "Claude", "entity_type": "tool"},
                    {"entity_id": "rag", "label": "RAG", "entity_type": "concept"},
                ]
            },
        )

        extractor = FactExtractor(api_key="test")
        result = extractor.extract("Claude is an AI tool used for RAG.")

        assert len(result.entities) == 2
        assert result.entities[0].entity_id == "claude"
        assert result.entities[1].label == "RAG"

    @patch("anthropic.Anthropic")
    def test_extract_facts(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_client.messages.create.return_value = _mock_tool_response(
            "extract_facts",
            {
                "facts": [
                    {
                        "subject": "user",
                        "predicate": "works_on",
                        "object_id": "second_brain",
                        "confidence": 0.95,
                    },
                    {
                        "subject": "user",
                        "predicate": "believes",
                        "object_literal": "bi-temporal modeling is important",
                        "valid_from": "2026-08-20",
                        "confidence": 0.8,
                    },
                ]
            },
        )

        result = FactExtractor(api_key="test").extract("User works on second brain project.")

        assert len(result.facts) == 2
        assert result.facts[0].subject == "user"
        assert result.facts[0].object_id == "second_brain"
        assert result.facts[1].object_literal == "bi-temporal modeling is important"
        assert result.facts[1].valid_from == "2026-08-20"

    @patch("anthropic.Anthropic")
    def test_extract_combined(self, mock_anthropic_cls):
        """Test extraction when both entities and facts are returned."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_client.messages.create.return_value = _mock_multi_tool_response([
            (
                "extract_entities",
                {
                    "entities": [
                        {"entity_id": "networkx", "label": "NetworkX", "entity_type": "tool"},
                    ]
                },
            ),
            (
                "extract_facts",
                {
                    "facts": [
                        {
                            "subject": "project",
                            "predicate": "uses",
                            "object_id": "networkx",
                        }
                    ]
                },
            ),
        ])

        result = FactExtractor(api_key="test").extract("The project uses NetworkX for graph storage.")

        assert len(result.entities) == 1
        assert len(result.facts) == 1
        assert result.facts[0].object_id == "networkx"

    @patch("anthropic.Anthropic")
    def test_entity_id_normalization(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_client.messages.create.return_value = _mock_tool_response(
            "extract_entities",
            {
                "entities": [
                    {"entity_id": "Transformer Architecture", "label": "Transformers", "entity_type": "technique"},
                ]
            },
        )

        result = FactExtractor(api_key="test").extract("Transformers are used in NLP.")
        assert result.entities[0].entity_id == "transformer_architecture"

    def test_empty_text(self):
        result = FactExtractor(api_key="test").extract("   ")
        assert result.entities == []
        assert result.facts == []

    @patch("anthropic.Anthropic")
    def test_raw_response_captured(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        # Include a text block along with tool calls
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "I found 2 entities and 3 facts."

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "extract_entities"
        tool_block.input = {"entities": []}

        mock_response = MagicMock()
        mock_response.content = [text_block, tool_block]
        mock_client.messages.create.return_value = mock_response

        result = FactExtractor(api_key="test").extract("Some text.")
        assert "found 2 entities" in result.raw_response
