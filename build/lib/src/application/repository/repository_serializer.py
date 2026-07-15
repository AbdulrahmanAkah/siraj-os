import json
from pathlib import Path

from src.domain.knowledge_graph.knowledge_edge import KnowledgeEdge
from src.domain.knowledge_graph.knowledge_graph import KnowledgeGraph
from src.domain.knowledge_graph.knowledge_node import KnowledgeNode
from src.domain.knowledge_objects.relationship import Relationship


class RepositorySerializer:
    """Serializes the canonical graph without introducing a second graph model."""

    GRAPH_FILE = "graph.json"
    METADATA_FILE = "metadata.json"
    PROJECTION_FILES = {
        "SOURCE": "sources.json",
        "DOCUMENT": "documents.json",
        "EVIDENCE": "evidence.json",
        "CLAIM": "claims.json",
    }

    def to_storage(self, graph):
        graph_data = graph.to_dict()
        projections = {
            filename: [node for node in graph_data["nodes"] if node["type"] == node_type]
            for node_type, filename in self.PROJECTION_FILES.items()
        }
        metadata = {
            "schema_version": 1,
            "node_count": len(graph_data["nodes"]),
            "relationship_count": len(graph_data["edges"]),
        }
        return {self.GRAPH_FILE: graph_data, self.METADATA_FILE: metadata, **projections}

    def save(self, path, graph):
        directory = Path(path)
        directory.mkdir(parents=True, exist_ok=True)
        for filename, payload in self.to_storage(graph).items():
            (directory / filename).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def load(self, path):
        graph_path = Path(path) / self.GRAPH_FILE
        if not graph_path.exists():
            return KnowledgeGraph()
        return self.from_graph_dict(json.loads(graph_path.read_text(encoding="utf-8")))

    @staticmethod
    def from_graph_dict(payload):
        graph = KnowledgeGraph(
            nodes=[
                KnowledgeNode(
                    id=node["id"],
                    type=node["type"],
                    data=node.get("data", {}),
                    metadata=node.get("metadata", {}),
                )
                for node in payload.get("nodes", [])
            ],
            edges=[
                KnowledgeEdge(
                    source=edge["source"],
                    target=edge["target"],
                    relation=edge["relation"],
                    metadata=edge.get("metadata", {}),
                    relationship_id=edge.get("relationship_id", ""),
                )
                for edge in payload.get("edges", [])
            ],
            relationships=[
                Relationship(
                    subject=relationship.get("subject", ""),
                    predicate=relationship.get("predicate", ""),
                    object=relationship.get("object", ""),
                    metadata=relationship.get("metadata", {}),
                )
                for relationship in payload.get("relationships", [])
            ],
        )
        graph.refresh()
        return graph

    def merge(self, existing, incoming):
        nodes = {node.id: node for node in existing.nodes}
        for node in incoming.nodes:
            if node.id in nodes:
                nodes[node.id] = self._merge_node(nodes[node.id], node)
            else:
                nodes[node.id] = node

        edges = {edge.relationship_id: edge for edge in existing.edges}
        for edge in incoming.edges:
            edges.setdefault(edge.relationship_id, edge)

        relationships = {
            self._relationship_key(relationship): relationship
            for relationship in existing.relationships
        }
        for relationship in incoming.relationships:
            relationships.setdefault(self._relationship_key(relationship), relationship)

        merged = KnowledgeGraph(
            nodes=list(nodes.values()),
            edges=list(edges.values()),
            relationships=list(relationships.values()),
        )
        merged.refresh()
        return merged

    @staticmethod
    def _relationship_key(relationship):
        payload = relationship.to_dict() if hasattr(relationship, "to_dict") else relationship
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)

    @classmethod
    def _merge_node(cls, existing, incoming):
        return KnowledgeNode(
            id=existing.id,
            type=existing.type,
            data=cls._merge_value(existing.data, incoming.data),
            metadata=cls._merge_value(existing.metadata, incoming.metadata),
        )

    @classmethod
    def _merge_value(cls, existing, incoming):
        if isinstance(existing, dict) and isinstance(incoming, dict):
            merged = dict(existing)
            for key, value in incoming.items():
                merged[key] = cls._merge_value(merged[key], value) if key in merged else value
            return merged
        if isinstance(existing, list) and isinstance(incoming, list):
            merged = list(existing)
            for value in incoming:
                if value not in merged:
                    merged.append(value)
            return merged
        return incoming if incoming not in (None, "", [], {}) else existing


__all__ = ["RepositorySerializer"]
