"""Scoring logic for the evaluation harness.

Compares system output against golden query expectations and produces
structured scores that can be aggregated into a results writeup.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

from backend.eval.golden_set import GoldenQuery


@dataclass
class QueryScore:
    """Score for a single query."""

    query: str
    query_type: str
    difficulty: str

    # Component scores (0.0 - 1.0)
    entity_recall: float = 0.0  # fraction of expected entities found
    predicate_recall: float = 0.0  # fraction of expected predicates traversed
    answer_relevance: float = 0.0  # fraction of expected substrings found
    temporal_accuracy: float = 0.0  # for point-in-time queries: did the answer reflect the right time?

    # Composite
    overall: float = 0.0

    # Details
    expected_entities: list[str] = field(default_factory=list)
    found_entities: list[str] = field(default_factory=list)
    expected_predicates: list[str] = field(default_factory=list)
    found_predicates: list[str] = field(default_factory=list)
    expected_answer_contains: list[str] = field(default_factory=list)
    answer_matches: list[str] = field(default_factory=list)
    answer_misses: list[str] = field(default_factory=list)
    notes: str = ""

    def compute_overall(self) -> float:
        """Compute weighted overall score."""
        weights = {
            "entity_recall": 0.25,
            "predicate_recall": 0.25,
            "answer_relevance": 0.40,
            "temporal_accuracy": 0.10,
        }
        # Only use temporal_accuracy for point-in-time and contradiction queries
        if self.query_type not in ("point_in_time", "contradiction"):
            # Redistribute temporal weight to answer_relevance
            weights["answer_relevance"] += weights["temporal_accuracy"]
            weights["temporal_accuracy"] = 0.0

        total_weight = sum(weights.values()) or 1.0
        self.overall = sum(
            getattr(self, field) * w for field, w in weights.items()
        ) / total_weight
        return self.overall


@dataclass
class EvalResult:
    """Aggregate result for the full eval run."""

    timestamp: str = ""
    total_queries: int = 0
    avg_overall: float = 0.0
    avg_by_type: dict[str, float] = field(default_factory=dict)
    avg_by_difficulty: dict[str, float] = field(default_factory=dict)
    query_scores: list[QueryScore] = field(default_factory=list)
    pass_rate: float = 0.0  # fraction with overall >= 0.5
    summary: str = ""


def score_entity_recall(
    expected: list[str],
    found_entities: list[str],
    found_predicates: list[str],
    found_text: str,
) -> tuple[float, list[str], list[str]]:
    """Score how many expected entities appear in the results.

    Checks entity IDs in found_entities and also does substring matching
    on the combined result text (in case entities appear by label, not ID).
    """
    if not expected:
        return 1.0, [], []

    found_set = set(found_entities)
    # Also check predicates and raw text for entity mentions
    all_text = (found_text + " " + " ".join(found_predicates)).lower()

    matched = []
    missed = []
    for eid in expected:
        eid_normalized = eid.lower().replace("_", " ")
        # Check direct ID match or substring in text
        if eid in found_set or eid_normalized in all_text or eid.replace("_", "") in all_text:
            matched.append(eid)
        else:
            missed.append(eid)

    recall = len(matched) / len(expected) if expected else 1.0
    return recall, matched, missed


def score_predicate_recall(
    expected: list[str],
    found_predicates: list[str],
    found_text: str,
) -> tuple[float, list[str], list[str]]:
    """Score how many expected predicates appear in the results."""
    if not expected:
        return 1.0, [], []

    found_set = {p.lower() for p in found_predicates}
    all_text = found_text.lower()

    matched = []
    missed = []
    for pred in expected:
        pred_norm = pred.lower().replace("_", " ")
        if pred.lower() in found_set or pred_norm in all_text:
            matched.append(pred)
        else:
            missed.append(pred)

    recall = len(matched) / len(expected) if expected else 1.0
    return recall, matched, missed


def score_answer_relevance(
    expected_substrings: list[str],
    result_texts: list[str],
) -> tuple[float, list[str], list[str]]:
    """Score how many expected substrings appear in the result texts."""
    if not expected_substrings:
        return 1.0, [], []

    combined_text = " ".join(result_texts).lower()

    matched = []
    missed = []
    for substr in expected_substrings:
        if substr.lower() in combined_text:
            matched.append(substr)
        else:
            missed.append(substr)

    relevance = len(matched) / len(expected_substrings) if expected_substrings else 1.0
    return relevance, matched, missed


def score_temporal_accuracy(
    query_type: str,
    golden: GoldenQuery,
    result_texts: list[str],
    result_metadatas: list[dict],
) -> float:
    """Score temporal accuracy for point-in-time queries.

    For point-in-time queries, check that the results contain temporal
    metadata consistent with the expected validity window.
    """
    if query_type not in ("point_in_time", "contradiction"):
        return 1.0  # not applicable

    combined = " ".join(result_texts).lower()

    # For contradiction queries, check that both old and new beliefs appear
    if query_type == "contradiction":
        expected = golden.expected_answer_contains
        if not expected:
            return 1.0
        matches = sum(1 for s in expected if s.lower() in combined)
        return matches / len(expected) if expected else 1.0

    # For point-in-time: check that valid_from metadata is present and reasonable
    has_temporal = any(
        m.get("valid_from") or m.get("recorded_at") for m in result_metadatas
    )
    if has_temporal:
        return 1.0

    # Check if the answer text itself contains date-like information
    import re
    date_pattern = r"\d{4}-\d{2}-\d{2}"
    has_dates = any(re.search(date_pattern, t) for t in result_texts)
    return 0.5 if has_dates else 0.0


def score_query(
    golden: GoldenQuery,
    result_texts: list[str],
    result_metadatas: list[dict],
    result_sources: list[str],
    found_entities: list[str] | None = None,
    found_predicates: list[str] | None = None,
) -> QueryScore:
    """Score a single query against its golden expectations."""
    found_entities = found_entities or []
    found_predicates = found_predicates or []
    combined_text = " ".join(result_texts)

    entity_recall, matched_entities, missed_entities = score_entity_recall(
        golden.expected_entities, found_entities, found_predicates, combined_text
    )

    predicate_recall, matched_predicates, missed_predicates = score_predicate_recall(
        golden.expected_predicates, found_predicates, combined_text
    )

    answer_relevance, answer_matches, answer_misses = score_answer_relevance(
        golden.expected_answer_contains, result_texts
    )

    temporal_accuracy = score_temporal_accuracy(
        golden.query_type, golden, result_texts, result_metadatas
    )

    score = QueryScore(
        query=golden.query,
        query_type=golden.query_type,
        difficulty=golden.difficulty,
        entity_recall=entity_recall,
        predicate_recall=predicate_recall,
        answer_relevance=answer_relevance,
        temporal_accuracy=temporal_accuracy,
        expected_entities=golden.expected_entities,
        found_entities=matched_entities,
        expected_predicates=golden.expected_predicates,
        found_predicates=matched_predicates,
        expected_answer_contains=golden.expected_answer_contains,
        answer_matches=answer_matches,
        answer_misses=answer_misses,
        notes=golden.notes,
    )
    score.compute_overall()
    return score


def aggregate_results(scores: list[QueryScore]) -> EvalResult:
    """Aggregate individual query scores into an EvalResult."""
    if not scores:
        return EvalResult(timestamp=datetime.now(timezone.utc).isoformat())

    avg_overall = sum(s.overall for s in scores) / len(scores)

    # By type
    by_type: dict[str, list[float]] = {}
    for s in scores:
        by_type.setdefault(s.query_type, []).append(s.overall)
    avg_by_type = {k: sum(v) / len(v) for k, v in by_type.items()}

    # By difficulty
    by_diff: dict[str, list[float]] = {}
    for s in scores:
        by_diff.setdefault(s.difficulty, []).append(s.overall)
    avg_by_difficulty = {k: sum(v) / len(v) for k, v in by_diff.items()}

    # Pass rate: overall >= 0.5
    pass_rate = sum(1 for s in scores if s.overall >= 0.5) / len(scores)

    # Build summary
    summary_lines = [
        f"Eval run: {len(scores)} queries",
        f"Overall accuracy: {avg_overall:.1%}",
        f"Pass rate (≥0.5): {pass_rate:.1%}",
        "",
        "By query type:",
    ]
    for qtype, avg in sorted(avg_by_type.items()):
        count = len(by_type[qtype])
        summary_lines.append(f"  {qtype}: {avg:.1%} ({count} queries)")
    summary_lines.append("")
    summary_lines.append("By difficulty:")
    for diff, avg in sorted(avg_by_difficulty.items()):
        count = len(by_diff[diff])
        summary_lines.append(f"  {diff}: {avg:.1%} ({count} queries)")

    return EvalResult(
        timestamp=datetime.now(timezone.utc).isoformat(),
        total_queries=len(scores),
        avg_overall=avg_overall,
        avg_by_type=avg_by_type,
        avg_by_difficulty=avg_by_difficulty,
        query_scores=scores,
        pass_rate=pass_rate,
        summary="\n".join(summary_lines),
    )


def save_results(result: EvalResult, path: str) -> None:
    """Save eval results to JSON."""
    data = {
        "timestamp": result.timestamp,
        "total_queries": result.total_queries,
        "avg_overall": result.avg_overall,
        "avg_by_type": result.avg_by_type,
        "avg_by_difficulty": result.avg_by_difficulty,
        "pass_rate": result.pass_rate,
        "summary": result.summary,
        "query_scores": [
            {
                "query": s.query,
                "query_type": s.query_type,
                "difficulty": s.difficulty,
                "overall": s.overall,
                "entity_recall": s.entity_recall,
                "predicate_recall": s.predicate_recall,
                "answer_relevance": s.answer_relevance,
                "temporal_accuracy": s.temporal_accuracy,
                "expected_entities": s.expected_entities,
                "found_entities": s.found_entities,
                "expected_predicates": s.expected_predicates,
                "found_predicates": s.found_predicates,
                "expected_answer_contains": s.expected_answer_contains,
                "answer_matches": s.answer_matches,
                "answer_misses": s.answer_misses,
            }
            for s in result.query_scores
        ],
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2))
