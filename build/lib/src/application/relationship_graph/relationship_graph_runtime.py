from hashlib import sha256
import json

from src.application.claim_extraction.models import ClaimExtractionResult
from src.application.entity_extraction.entity_extraction_runtime import (
    EntityExtractionRuntime,
)
from src.application.entity_extraction.models import EntityExtractionResult
from src.application.event_extraction.event_extraction_runtime import (
    EventExtractionRuntime,
)
from src.application.event_extraction.models import EventExtractionResult

from .models import (
    GraphEdge,
    GraphNode,
    RelationshipCandidate,
    RelationshipGraph,
    RelationshipGraphResult,
)


class RelationshipGraphRuntime:
    """Builds a deterministic, traceable graph from claim/entity/event records."""

    NODE_TYPES = ("ENTITY_NODE", "EVENT_NODE", "CLAIM_NODE")
    EDGE_TYPES = (
        "SUPPORTED_BY",
        "REFERENCES",
        "ASSOCIATED_WITH",
        "LOCATED_IN",
        "OCCURRED_ON",
    )

    def __init__(
        self,
        entity_extraction_runtime,
        event_extraction_runtime,
    ):
        if not isinstance(entity_extraction_runtime, EntityExtractionRuntime):
            raise TypeError(
                "RelationshipGraphRuntime requires an EntityExtractionRuntime"
            )
        if not isinstance(event_extraction_runtime, EventExtractionRuntime):
            raise TypeError(
                "RelationshipGraphRuntime requires an EventExtractionRuntime"
            )
        self.entity_extraction_runtime = entity_extraction_runtime
        self.event_extraction_runtime = event_extraction_runtime

    def execute_relationship_graph(
        self,
        graph_plan,
        claim_extraction_result,
        entity_extraction_result,
        event_extraction_result,
    ):
        self.validate_runtime_inputs_or_raise(
            graph_plan,
            claim_extraction_result,
            entity_extraction_result,
            event_extraction_result,
        )
        nodes = self.generate_nodes(
            claim_extraction_result,
            entity_extraction_result,
            event_extraction_result,
        )
        candidates = self.generate_relationship_candidates(
            claim_extraction_result,
            entity_extraction_result,
            event_extraction_result,
            nodes,
        )
        edges = self.generate_edges(candidates)
        graph = RelationshipGraph(
            graph_id=graph_plan.graph_id,
            claim_extraction_result_id=graph_plan.claim_extraction_result_id,
            entity_extraction_result_id=graph_plan.entity_extraction_result_id,
            event_extraction_result_id=graph_plan.event_extraction_result_id,
            nodes=nodes,
            edges=edges,
            node_count=len(nodes),
            edge_count=len(edges),
        )
        result = self.build_graph_result(graph, candidates)
        if not self.validate_graph(
            graph_plan,
            claim_extraction_result,
            entity_extraction_result,
            event_extraction_result,
            result,
        ):
            raise ValueError("Invalid relationship graph result")
        return result

    def build_graph(self, *args):
        return self.execute_relationship_graph(*args)

    def generate_nodes(
        self,
        claim_extraction_result,
        entity_extraction_result,
        event_extraction_result,
    ):
        nodes = []
        nodes.extend(
            self._node("CLAIM_NODE", claim.claim_id)
            for claim in claim_extraction_result.claims
        )
        nodes.extend(
            self._node("ENTITY_NODE", entity.entity_id)
            for entity in entity_extraction_result.entities
        )
        nodes.extend(
            self._node("EVENT_NODE", event.event_id)
            for event in event_extraction_result.events
        )
        unique = {node.node_id: node for node in nodes}
        return [unique[node_id] for node_id in sorted(unique)]

    def generate_relationship_candidates(
        self,
        claim_extraction_result,
        entity_extraction_result,
        event_extraction_result,
        nodes=None,
    ):
        entity_by_id = {
            entity.entity_id: entity
            for entity in entity_extraction_result.entities
        }
        candidates = []
        for entity in entity_extraction_result.entities:
            for claim_id in entity.source_claim_ids:
                candidates.append(
                    self._candidate(
                        "REFERENCES",
                        self._node_id("CLAIM_NODE", claim_id),
                        self._node_id("ENTITY_NODE", entity.entity_id),
                    )
                )
        for event in event_extraction_result.events:
            for claim_id in event.source_claim_ids:
                candidates.append(
                    self._candidate(
                        "SUPPORTED_BY",
                        self._node_id("EVENT_NODE", event.event_id),
                        self._node_id("CLAIM_NODE", claim_id),
                    )
                )
            for entity_id in event.source_entity_ids:
                candidates.append(
                    self._candidate(
                        "ASSOCIATED_WITH",
                        self._node_id("EVENT_NODE", event.event_id),
                        self._node_id("ENTITY_NODE", entity_id),
                    )
                )
                entity = entity_by_id.get(entity_id)
                if entity is None:
                    continue
                specialized_type = {
                    "LOCATION": "LOCATED_IN",
                    "DATE": "OCCURRED_ON",
                }.get(entity.entity_type)
                if specialized_type:
                    candidates.append(
                        self._candidate(
                            specialized_type,
                            self._node_id("EVENT_NODE", event.event_id),
                            self._node_id("ENTITY_NODE", entity_id),
                        )
                    )
        unique = {
            (candidate.edge_type, candidate.source_node_id, candidate.target_node_id): candidate
            for candidate in candidates
        }
        return [unique[key] for key in sorted(unique)]

    def generate_edges(self, candidates):
        edges = [
            GraphEdge(
                edge_id=self._edge_id(
                    candidate.edge_type,
                    candidate.source_node_id,
                    candidate.target_node_id,
                ),
                edge_type=candidate.edge_type,
                source_node_id=candidate.source_node_id,
                target_node_id=candidate.target_node_id,
            )
            for candidate in candidates
        ]
        unique = {edge.edge_id: edge for edge in edges}
        return [unique[edge_id] for edge_id in sorted(unique)]

    def build_graph_result(self, graph, candidates):
        material = {
            "graph_id": graph.graph_id,
            "node_ids": [node.node_id for node in graph.nodes],
            "edge_ids": [edge.edge_id for edge in graph.edges],
        }
        result_id = (
            f"relationship_graph_result_"
            f"{sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode('utf-8')).hexdigest()[:16]}"
        )
        return RelationshipGraphResult(
            result_id=result_id,
            graph=graph,
            relationship_candidates=list(candidates),
            node_count=graph.node_count,
            edge_count=graph.edge_count,
        )

    def validate_graph(
        self,
        graph_plan,
        claim_extraction_result,
        entity_extraction_result,
        event_extraction_result,
        graph_result,
    ):
        if not self._validate_plan(graph_plan):
            return False
        if not self._validate_inputs(
            graph_plan,
            claim_extraction_result,
            entity_extraction_result,
            event_extraction_result,
        ):
            return False
        if not isinstance(graph_result, RelationshipGraphResult):
            return False
        graph = graph_result.graph
        if graph.node_count != len(graph.nodes) or graph.edge_count != len(graph.edges):
            return False
        if graph_result.node_count != graph.node_count or graph_result.edge_count != graph.edge_count:
            return False
        node_ids = [node.node_id for node in graph.nodes]
        if len(node_ids) != len(set(node_ids)):
            return False
        if any(
            node.node_type not in self.NODE_TYPES
            or node.node_id != self._node_id(node.node_type, node.source_id)
            for node in graph.nodes
        ):
            return False
        edge_ids = [edge.edge_id for edge in graph.edges]
        if len(edge_ids) != len(set(edge_ids)):
            return False
        valid_nodes = set(node_ids)
        if any(
            edge.edge_type not in self.EDGE_TYPES
            or edge.source_node_id not in valid_nodes
            or edge.target_node_id not in valid_nodes
            or edge.edge_id
            != self._edge_id(edge.edge_type, edge.source_node_id, edge.target_node_id)
            for edge in graph.edges
        ):
            return False
        candidate_ids = [candidate.candidate_id for candidate in graph_result.relationship_candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            return False
        expected_candidates = self.generate_relationship_candidates(
            claim_extraction_result,
            entity_extraction_result,
            event_extraction_result,
            graph.nodes,
        )
        if graph_result.relationship_candidates != expected_candidates:
            return False
        expected_edges = self.generate_edges(expected_candidates)
        if graph.edges != expected_edges:
            return False
        return True

    def validate_runtime_inputs_or_raise(
        self,
        graph_plan,
        claim_extraction_result,
        entity_extraction_result,
        event_extraction_result,
    ):
        if not self._validate_plan(graph_plan):
            raise ValueError("Invalid relationship graph plan")
        if not self._validate_inputs(
            graph_plan,
            claim_extraction_result,
            entity_extraction_result,
            event_extraction_result,
        ):
            raise ValueError("Invalid graph extraction inputs")

    @staticmethod
    def _node(node_type, source_id):
        return GraphNode(
            node_id=RelationshipGraphRuntime._node_id(node_type, source_id),
            node_type=node_type,
            source_id=source_id,
        )

    @staticmethod
    def _node_id(node_type, source_id):
        return f"{node_type.lower()}_{source_id}"

    @staticmethod
    def _candidate(edge_type, source_node_id, target_node_id):
        material = "\x00".join([edge_type, source_node_id, target_node_id])
        return RelationshipCandidate(
            candidate_id=f"relationship_candidate_{sha256(material.encode('utf-8')).hexdigest()[:16]}",
            edge_type=edge_type,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
        )

    @staticmethod
    def _edge_id(edge_type, source_node_id, target_node_id):
        material = "\x00".join([edge_type, source_node_id, target_node_id])
        return f"edge_{sha256(material.encode('utf-8')).hexdigest()[:16]}"

    @staticmethod
    def _validate_plan(graph):
        return (
            isinstance(graph, RelationshipGraph)
            and bool(graph.graph_id)
            and bool(graph.claim_extraction_result_id)
            and bool(graph.entity_extraction_result_id)
            and bool(graph.event_extraction_result_id)
        )

    @staticmethod
    def _validate_inputs(plan, claims, entities, events):
        return (
            isinstance(claims, ClaimExtractionResult)
            and isinstance(entities, EntityExtractionResult)
            and isinstance(events, EventExtractionResult)
            and plan.claim_extraction_result_id == claims.result_id
            and plan.entity_extraction_result_id == entities.result_id
            and plan.event_extraction_result_id == events.result_id
            and claims.claim_count == len(claims.claims)
            and entities.entity_count == len(entities.entities)
            and events.event_count == len(events.events)
        )


__all__ = ["RelationshipGraphRuntime"]
