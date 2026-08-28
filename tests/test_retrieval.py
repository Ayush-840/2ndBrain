"""Tests for hybrid retrieval."""

from backend.retrieval.hybrid import reciprocal_rank_fusion


class TestReciprocalRankFusion:
    def test_single_list(self):
        ranked = [[{"id": "a", "text": "", "metadata": {}}, {"id": "b", "text": "", "metadata": {}}, {"id": "c", "text": "", "metadata": {}}]]
        merged = reciprocal_rank_fusion(ranked, weights=[1.0])
        ids = [r["id"] for r in merged]
        assert ids == ["a", "b", "c"]

    def test_fusion_combines_ranks(self):
        # List 1 ranks: a=1, b=2, c=3
        # List 2 ranks: c=1, a=2, b=3
        list1 = [{"id": "a", "text": "ta", "metadata": {}}, {"id": "b", "text": "tb", "metadata": {}}, {"id": "c", "text": "tc", "metadata": {}}]
        list2 = [{"id": "c", "text": "tc", "metadata": {}}, {"id": "a", "text": "ta", "metadata": {}}, {"id": "b", "text": "tb", "metadata": {}}]

        merged = reciprocal_rank_fusion([list1, list2], weights=[1.0, 1.0])
        # "a" has rank 1 in list1 and rank 2 in list2 — best combined
        # "c" has rank 3 in list1 and rank 1 in list2
        ids = [r["id"] for r in merged]
        # a should be first or second (appears well in both)
        assert "a" in ids[:2]
        assert len(ids) == 3

    def test_weight_affects_order(self):
        list1 = [{"id": "a", "text": "", "metadata": {}}]
        list2 = [{"id": "b", "text": "", "metadata": {}}]

        # Heavily weight list1 → "a" wins
        merged = reciprocal_rank_fusion([list1, list2], weights=[10.0, 1.0])
        assert merged[0]["id"] == "a"

        # Heavily weight list2 → "b" wins
        merged = reciprocal_rank_fusion([list1, list2], weights=[1.0, 10.0])
        assert merged[0]["id"] == "b"

    def test_empty_lists(self):
        merged = reciprocal_rank_fusion([], [])
        assert merged == []
