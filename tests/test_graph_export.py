"""Tests for Cytoscape.js graph export."""

from backend.memory.graph import TemporalGraph


class TestCytoscapeExport:
    """Test the export logic directly (mirrors routes_graph.export_graph)."""

    def _export(
        self,
        graph: TemporalGraph,
        *,
        valid_as_of: str | None = None,
        entity_type: str | None = None,
        include_superseded: bool = False,
    ) -> list[dict]:
        """Replicate the export logic from the route for testing."""
        if valid_as_of:
            facts = graph.query_as_of(valid_as_of)
        else:
            facts = graph.query_all_facts(include_superseded=include_superseded)

        elements: list[dict] = []
        seen_nodes: set[str] = set()

        for fact in facts:
            subject_id = fact["subject"]
            object_id = fact["object"]

            # Add subject node (skip if filtered out, but still add edge)
            if subject_id not in seen_nodes and not subject_id.startswith("_literal:"):
                entity = graph.get_entity(subject_id)
                if entity:
                    etype = entity.get("entity_type", "concept")
                    if not (entity_type and etype != entity_type):
                        elements.append({
                            "group": "nodes",
                            "data": {
                                "id": subject_id,
                                "label": entity.get("label", subject_id),
                                "entity_type": etype,
                            },
                        })
                        seen_nodes.add(subject_id)

            # Add object node (skip if filtered out, but still add edge)
            if object_id not in seen_nodes:
                if object_id.startswith("_literal:"):
                    elements.append({
                        "group": "nodes",
                        "data": {"id": object_id, "label": object_id[10:50], "entity_type": "literal"},
                    })
                    seen_nodes.add(object_id)
                else:
                    entity = graph.get_entity(object_id)
                    if entity:
                        etype = entity.get("entity_type", "concept")
                        if not (entity_type and etype != entity_type):
                            elements.append({
                                "group": "nodes",
                                "data": {"id": object_id, "label": entity["label"], "entity_type": entity["entity_type"]},
                            })
                            seen_nodes.add(object_id)

            # Add edge
            elements.append({
                "group": "edges",
                "data": {
                    "id": fact.get("fact_id", ""),
                    "source": subject_id,
                    "target": object_id,
                    "predicate": fact.get("predicate", ""),
                },
            })

        return elements

    def setup_method(self):
        self.graph = TemporalGraph()
        self.graph.add_entity("user", "Ayush", "person")
        self.graph.add_entity("rag", "RAG", "concept")
        self.graph.add_entity("graph_db", "Graph Database", "concept")
        self.graph.add_entity("neo4j", "Neo4j", "tool")

        self.graph.add_fact("user", "works_on", object_id="rag", valid_from="2026-03-01")
        self.graph.add_fact("user", "believes", object_literal="graph > vectors", valid_from="2026-07-15")
        self.graph.add_fact("rag", "uses", object_id="graph_db")
        self.graph.add_fact("graph_db", "built_with", object_id="neo4j")

    def test_export_produces_cytoscape_format(self):
        elements = self._export(self.graph)
        assert len(elements) > 0
        for el in elements:
            assert "group" in el
            assert "data" in el
            assert el["group"] in ("nodes", "edges")

    def test_nodes_have_required_fields(self):
        elements = self._export(self.graph)
        nodes = [e for e in elements if e["group"] == "nodes"]
        for node in nodes:
            assert "id" in node["data"]
            assert "label" in node["data"]
            assert "entity_type" in node["data"]

    def test_edges_have_source_target(self):
        elements = self._export(self.graph)
        edges = [e for e in elements if e["group"] == "edges"]
        assert len(edges) >= 4
        for edge in edges:
            assert "source" in edge["data"]
            assert "target" in edge["data"]
            assert "predicate" in edge["data"]

    def test_literal_nodes_included(self):
        elements = self._export(self.graph)
        nodes = [e for e in elements if e["group"] == "nodes"]
        literal_nodes = [n for n in nodes if n["data"]["entity_type"] == "literal"]
        assert len(literal_nodes) >= 1
        # The literal label should be truncated, not the full ID
        assert not literal_nodes[0]["data"]["label"].startswith("_literal:")

    def test_no_duplicate_nodes(self):
        elements = self._export(self.graph)
        nodes = [e for e in elements if e["group"] == "nodes"]
        node_ids = [n["data"]["id"] for n in nodes]
        assert len(node_ids) == len(set(node_ids))

    def test_entity_type_filter(self):
        # Filter to only tool-type nodes
        elements = self._export(self.graph, entity_type="tool")
        nodes = [e for e in elements if e["group"] == "nodes"]
        node_types = {n["data"]["entity_type"] for n in nodes}
        # Only tool nodes should appear
        assert "tool" in node_types
        assert "person" not in node_types
        assert "concept" not in node_types

    def test_superseded_excluded_by_default(self):
        # Add a fact, then supersede it
        old_id = self.graph.add_fact("user", "status", object_literal="v1", valid_from="2026-01-01")
        result = self.graph.supersede_and_add("user", "status", object_literal="v2", valid_from="2026-06-01")

        elements = self._export(self.graph)
        edge_ids = [e["data"]["id"] for e in elements if e["group"] == "edges"]
        assert old_id not in edge_ids  # superseded edge excluded
        assert result["new_fact_id"] in edge_ids  # new edge included

    def test_superseded_included_when_requested(self):
        old_id = self.graph.add_fact("user", "status", object_literal="v1", valid_from="2026-01-01")
        self.graph.supersede_and_add("user", "status", object_literal="v2", valid_from="2026-06-01")

        elements = self._export(self.graph, include_superseded=True)
        edge_ids = [e["data"]["id"] for e in elements if e["group"] == "edges"]
        assert old_id in edge_ids  # now included

    def test_point_in_time_export(self):
        # In May, only the "works_on" fact is valid (before "believes" starts)
        may_elements = self._export(self.graph, valid_as_of="2026-05-01")
        predicates_may = {
            e["data"]["predicate"] for e in may_elements if e["group"] == "edges"
        }
        assert "works_on" in predicates_may
        assert "believes" not in predicates_may  # valid_from=2026-07-15, not yet

    def test_counts(self):
        elements = self._export(self.graph)
        nodes = [e for e in elements if e["group"] == "nodes"]
        edges = [e for e in elements if e["group"] == "edges"]
        assert len(nodes) >= 4  # user, rag, graph_db, neo4j
        assert len(edges) >= 4
