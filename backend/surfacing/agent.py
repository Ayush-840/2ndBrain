"""Surfacing agent: finds insights, flags contradictions, and generates digests.

Three core capabilities:
  1. Contradiction detection: flags when new facts conflict with existing ones
  2. Resurfacing: finds stale-but-relevant notes based on current context
  3. Digest generation: daily/weekly summaries of graph activity
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone, timedelta

from backend.memory.graph import TemporalGraph
from backend.memory.community import CommunityStore

logger = logging.getLogger(__name__)


@dataclass
class ContradictionFlag:
    """A detected contradiction between two facts."""

    old_fact_id: str
    new_fact_id: str
    subject: str
    predicate: str
    old_value: str
    new_value: str
    old_valid_from: str | None = None
    new_valid_from: str | None = None
    detected_at: str = ""
    severity: str = "info"  # "info", "warning", "critical"

    def __post_init__(self):
        if not self.detected_at:
            self.detected_at = datetime.now(timezone.utc).isoformat()


@dataclass
class ResurfacedNote:
    """A note resurfaced because it's relevant to current context."""

    fact_id: str
    subject: str
    predicate: str
    object_value: str
    text: str  # human-readable
    relevance_score: float = 0.0
    reason: str = ""  # why it was resurfaced
    last_seen: str | None = None
    recorded_at: str | None = None


@dataclass
class DigestEntry:
    """A single entry in a digest report."""

    category: str  # "new_facts", "contradictions", "resurfaced", "community_update"
    title: str
    description: str
    fact_ids: list[str] = field(default_factory=list)
    timestamp: str = ""


@dataclass
class Digest:
    """A daily or weekly digest report."""

    digest_type: str  # "daily" or "weekly"
    generated_at: str = ""
    period_start: str = ""
    period_end: str = ""
    entries: list[DigestEntry] = field(default_factory=list)
    summary: str = ""

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()


class SurfacingAgent:
    """Orchestrates surfacing tasks: contradictions, resurfacing, digests."""

    def __init__(
        self,
        graph: TemporalGraph,
        community: CommunityStore | None = None,
    ):
        self._graph = graph
        self._community = community
        # document_id → ISO date we last nudged about it (once/day cap)
        self._reminded: dict[str, str] = {}

    def detect_contradictions(
        self,
        since: str | None = None,
    ) -> list[ContradictionFlag]:
        """Scan the graph for contradictions.

        Finds pairs of facts with the same subject+predicate but different
        objects that have overlapping validity windows.

        Args:
            since: Only check facts recorded after this ISO8601 date.
        """
        from backend.memory.graph import _parse_date, _dates_overlap

        since_dt = _parse_date(since) if since else None
        flags: list[ContradictionFlag] = []
        seen_pairs: set[tuple[str, str, str]] = set()

        # Get all active facts
        facts = self._graph.query_all_facts(include_superseded=False)

        # Group by (subject, predicate)
        by_sp: dict[tuple[str, str], list[dict]] = {}
        for fact in facts:
            key = (fact.get("subject", ""), fact.get("predicate", ""))
            by_sp.setdefault(key, []).append(fact)

        # Find contradictions within each group
        for (subject, predicate), group in by_sp.items():
            for i, fact_a in enumerate(group):
                for fact_b in group[i + 1:]:
                    obj_a = fact_a.get("object_literal") or fact_a.get("object", "")
                    obj_b = fact_b.get("object_literal") or fact_b.get("object", "")

                    # Same object → not a contradiction
                    if obj_a == obj_b:
                        continue

                    # Already processed this pair
                    pair_key = tuple(sorted([fact_a.get("fact_id", ""), fact_b.get("fact_id", "")]))
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)

                    # Check temporal overlap
                    if not _dates_overlap(
                        fact_a.get("valid_from"), fact_a.get("valid_to"),
                        fact_b.get("valid_from"), fact_b.get("valid_to"),
                    ):
                        continue

                    # Check since filter
                    if since_dt:
                        recorded_a = _parse_date(fact_a.get("recorded_at"))
                        recorded_b = _parse_date(fact_b.get("recorded_at"))
                        if (recorded_a and recorded_a < since_dt) and \
                           (recorded_b and recorded_b < since_dt):
                            continue

                    # Determine severity
                    severity = "info"
                    if predicate in ("believes", "prefers", "trusts"):
                        severity = "warning"

                    flags.append(ContradictionFlag(
                        old_fact_id=fact_a.get("fact_id", ""),
                        new_fact_id=fact_b.get("fact_id", ""),
                        subject=subject,
                        predicate=predicate,
                        old_value=obj_a,
                        new_value=obj_b,
                        old_valid_from=fact_a.get("valid_from"),
                        new_valid_from=fact_b.get("valid_from"),
                        severity=severity,
                    ))

        return flags

    def resurface_relevant(
        self,
        context: str = "",
        top_k: int = 10,
        max_age_days: int = 30,
    ) -> list[ResurfacedNote]:
        """Find facts that are stale but potentially relevant.

        A fact is "stale" if it was recorded more than max_age_days ago
        and hasn't been accessed recently. Relevance is scored by how
        closely it matches the current context.
        """
        from backend.enrichment.embedder import embed_texts
        from backend.memory.graph import _parse_date
        import numpy as np

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=max_age_days)

        facts = self._graph.query_all_facts(include_superseded=False)
        if not facts:
            return []

        # Filter to old facts
        old_facts = []
        for fact in facts:
            recorded = _parse_date(fact.get("recorded_at"))
            if recorded and recorded < cutoff:
                old_facts.append(fact)

        if not old_facts:
            return []

        # Build text representations
        from backend.memory.community import _fact_to_graph_text
        texts = [_fact_to_graph_text(f, self._graph) for f in old_facts]

        # Score relevance if context provided
        if context:
            all_texts = texts + [context]
            embeddings = np.array(embed_texts(all_texts))
            query_emb = embeddings[-1]
            fact_embs = embeddings[:-1]

            # Cosine similarity
            scores = fact_embs @ query_emb
        else:
            scores = np.ones(len(texts))

        # Rank by score
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]

        results: list[ResurfacedNote] = []
        for idx, score in ranked:
            fact = old_facts[idx]
            text = texts[idx]
            subj = fact.get("subject", "")
            obj = fact.get("object_literal") or fact.get("object", "")

            # Resolve labels
            subj_entity = self._graph.get_entity(subj)
            if subj_entity:
                subj = subj_entity.get("label", subj)

            reason = "Stale fact relevant to current context"
            if score > 0.7:
                reason = "Highly relevant stale fact"
            elif score > 0.5:
                reason = "Moderately relevant stale fact"

            results.append(ResurfacedNote(
                fact_id=fact.get("fact_id", ""),
                subject=subj,
                predicate=fact.get("predicate", ""),
                object_value=obj,
                text=text,
                relevance_score=float(score),
                reason=reason,
                recorded_at=fact.get("recorded_at"),
            ))

        return results

    def documents_needing_attention(
        self,
        within_days: int | None = None,
    ) -> list[dict]:
        """Documents with an approaching expiry / renewal / deadline.

        Both the Digest page section and the WhatsApp nudge read this same
        list, so the dashboard and the message can never disagree.
        """
        from backend.config import settings

        window = within_days or settings.document_expiry_warning_days
        return self._graph.documents_expiring(window)

    def push_document_reminders(self, within_days: int | None = None) -> list[dict]:
        """Send a WhatsApp nudge for documents about to go stale.

        Only the "red"/"amber" ones, and at most once per document per day.
        Silently a no-op when WhatsApp isn't configured.
        """
        from backend.config import settings
        from backend.ingestion.whatsapp import WhatsAppClient

        if not settings.whatsapp_enabled or not settings.whatsapp_allowed_sender:
            return []

        today = datetime.now(timezone.utc).date().isoformat()
        sent: list[dict] = []
        client = WhatsAppClient()

        for doc in self.documents_needing_attention(within_days):
            if doc.get("status") == "green":
                continue
            if self._reminded.get(doc.get("document_id")) == today:
                continue

            days_left = doc.get("days_left")
            if days_left is None:
                continue
            if days_left < 0:
                timeline = f"expired {abs(days_left)} days ago"
            elif days_left == 0:
                timeline = "expires today"
            else:
                timeline = f"expires in {days_left} days"

            body = (
                f"⏰ {doc.get('title', 'A document')} — {timeline}.\n"
                f"For: {doc.get('usage_context') or 'no purpose recorded'}"
            )

            if client.send_text(settings.whatsapp_allowed_sender, body):
                self._reminded[doc.get("document_id")] = today
                sent.append(doc)

        return sent

    def generate_digest(
        self,
        digest_type: str = "daily",
        since: str | None = None,
    ) -> Digest:
        """Generate a digest report.

        Args:
            digest_type: "daily" or "weekly"
            since: Start of the reporting period. Defaults to 24h (daily) or 7d (weekly).
        """
        now = datetime.now(UTC)

        if since is None:
            if digest_type == "weekly":
                since = (now - timedelta(days=7)).isoformat()
            else:
                since = (now - timedelta(days=1)).isoformat()

        entries: list[DigestEntry] = []

        # 1. New facts since the period
        new_facts = self._graph.query_all_facts(include_superseded=False)
        from backend.memory.graph import _parse_date
        since_dt = _parse_date(since)

        recent_facts = []
        for f in new_facts:
            recorded = _parse_date(f.get("recorded_at"))
            if since_dt and recorded and recorded >= since_dt:
                recent_facts.append(f)

        if recent_facts:
            entries.append(DigestEntry(
                category="new_facts",
                title=f"{len(recent_facts)} new facts added",
                description=f"Since {since[:10]}, {len(recent_facts)} new facts were extracted and stored.",
                fact_ids=[f.get("fact_id", "") for f in recent_facts[:20]],
                timestamp=now.isoformat(),
            ))

        # 2. Contradictions
        contradictions = self.detect_contradictions(since=since)
        if contradictions:
            entries.append(DigestEntry(
                category="contradictions",
                title=f"{len(contradictions)} contradictions detected",
                description="\n".join(
                    f"• {c.subject} {c.predicate}: '{c.old_value}' → '{c.new_value}'"
                    for c in contradictions[:5]
                ),
                fact_ids=[c.old_fact_id for c in contradictions],
                timestamp=now.isoformat(),
            ))

        # 2b. Documents needing attention (Phase 7)
        attention = self.documents_needing_attention()
        if attention:
            entries.append(DigestEntry(
                category="documents",
                title=f"{len(attention)} documents needing attention",
                description="\n".join(
                    f"• {d.get('title', 'document')} — "
                    + (f"expires in {d['days_left']}d" if (d.get("days_left") or 0) >= 0
                       else f"expired {abs(d.get('days_left', 0))}d ago")
                    for d in attention[:5]
                ),
                fact_ids=[d.get("document_id", "") for d in attention],
                timestamp=now.isoformat(),
            ))

        # 3. Community updates
        if self._community:
            stats = self._community.stats()
            if stats["clusters"] > 0:
                entries.append(DigestEntry(
                    category="community_update",
                    title=f"{stats['clusters']} topic clusters active",
                    description=f"Covering {stats['facts_in_clusters']} facts across {stats['clusters']} topics.",
                    timestamp=now.isoformat(),
                ))

        # 4. Graph stats
        graph_stats = self._graph.stats()
        entries.append(DigestEntry(
            category="graph_stats",
            title="Graph overview",
            description=(
                f"{graph_stats['entities']} entities, "
                f"{graph_stats['active_facts']} active facts "
                f"({graph_stats['facts']} total)"
            ),
            timestamp=now.isoformat(),
        ))

        # Build summary
        summary_parts = [e.title for e in entries]
        summary = f"{'Daily' if digest_type == 'daily' else 'Weekly'} digest: " + "; ".join(summary_parts)

        return Digest(
            digest_type=digest_type,
            generated_at=now.isoformat(),
            period_start=since,
            period_end=now.isoformat(),
            entries=entries,
            summary=summary,
        )
