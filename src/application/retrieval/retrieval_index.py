from collections import defaultdict


class RetrievalIndex:
    """Read-only in-memory indexes for a loaded canonical knowledge graph."""

    def __init__(self, graph):
        self.nodes_by_id = {}
        self.edges_by_id = {}
        self.nodes_by_type = defaultdict(list)
        self.claims_by_id = {}
        self.sources_by_id = {}
        self.documents_by_id = {}
        self.evidence_by_id = {}
        self.outgoing_by_node_id = defaultdict(list)
        self.incoming_by_node_id = defaultdict(list)
        self.build(graph)

    def build(self, graph):
        for node in graph.nodes:
            self.nodes_by_id[node.id] = node
            self.nodes_by_type[node.type].append(node)
            data = node.data if isinstance(node.data, dict) else {}
            if node.type == "CLAIM":
                self.claims_by_id[data.get("claim_id") or node.id] = node
            elif node.type == "SOURCE":
                self.sources_by_id[data.get("source_id") or node.id] = node
            elif node.type == "DOCUMENT":
                self.documents_by_id[data.get("document_id") or node.id] = node
            elif node.type == "EVIDENCE":
                self.evidence_by_id[data.get("evidence_id") or node.id] = node

        for edge in graph.edges:
            self.edges_by_id[edge.relationship_id] = edge
            self.outgoing_by_node_id[edge.source].append(edge)
            self.incoming_by_node_id[edge.target].append(edge)


__all__ = ["RetrievalIndex"]
