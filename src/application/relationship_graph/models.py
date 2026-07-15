from dataclasses import dataclass, field


@dataclass
class GraphNode:
    node_id: str
    node_type: str
    source_id: str


@dataclass
class GraphEdge:
    edge_id: str
    edge_type: str
    source_node_id: str
    target_node_id: str


@dataclass
class RelationshipCandidate:
    candidate_id: str
    edge_type: str
    source_node_id: str
    target_node_id: str


@dataclass
class RelationshipGraph:
    graph_id: str
    claim_extraction_result_id: str = ""
    entity_extraction_result_id: str = ""
    event_extraction_result_id: str = ""
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0


@dataclass
class RelationshipGraphResult:
    result_id: str
    graph: RelationshipGraph
    relationship_candidates: list[RelationshipCandidate] = field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0


__all__ = [
    "GraphEdge",
    "GraphNode",
    "RelationshipCandidate",
    "RelationshipGraph",
    "RelationshipGraphResult",
]
