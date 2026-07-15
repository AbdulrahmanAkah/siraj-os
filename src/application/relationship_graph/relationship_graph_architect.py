from hashlib import sha256
import json

from src.application.entity_extraction.entity_extraction_runtime import (
    EntityExtractionRuntime,
)
from src.application.event_extraction.event_extraction_runtime import (
    EventExtractionRuntime,
)
from src.application.claim_extraction.models import ClaimExtractionResult
from src.application.entity_extraction.models import EntityExtractionResult
from src.application.event_extraction.models import EventExtractionResult

from .models import RelationshipGraph


class RelationshipGraphArchitect:
    """Defines deterministic graph construction over claims, entities, and events."""

    def __init__(
        self,
        entity_extraction_runtime,
        event_extraction_runtime,
    ):
        if not isinstance(entity_extraction_runtime, EntityExtractionRuntime):
            raise TypeError(
                "RelationshipGraphArchitect requires an EntityExtractionRuntime"
            )
        if not isinstance(event_extraction_runtime, EventExtractionRuntime):
            raise TypeError(
                "RelationshipGraphArchitect requires an EventExtractionRuntime"
            )
        self.entity_extraction_runtime = entity_extraction_runtime
        self.event_extraction_runtime = event_extraction_runtime

    def build_relationship_graph_plan(
        self,
        claim_extraction_result=None,
        entity_extraction_result=None,
        event_extraction_result=None,
    ):
        claim_result_id = (
            claim_extraction_result.result_id
            if isinstance(claim_extraction_result, ClaimExtractionResult)
            else "default_claim_extraction"
        )
        entity_result_id = (
            entity_extraction_result.result_id
            if isinstance(entity_extraction_result, EntityExtractionResult)
            else "default_entity_extraction"
        )
        event_result_id = (
            event_extraction_result.result_id
            if isinstance(event_extraction_result, EventExtractionResult)
            else "default_event_extraction"
        )
        material = {
            "claim_result_id": claim_result_id,
            "entity_result_id": entity_result_id,
            "event_result_id": event_result_id,
        }
        graph_id = (
            f"relationship_graph_"
            f"{sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode('utf-8')).hexdigest()[:16]}"
        )
        return RelationshipGraph(
            graph_id=graph_id,
            claim_extraction_result_id=claim_result_id,
            entity_extraction_result_id=entity_result_id,
            event_extraction_result_id=event_result_id,
        )

    def validate_plan(self, graph):
        return (
            isinstance(graph, RelationshipGraph)
            and bool(graph.graph_id)
            and bool(graph.claim_extraction_result_id)
            and bool(graph.entity_extraction_result_id)
            and bool(graph.event_extraction_result_id)
        )


__all__ = ["RelationshipGraphArchitect"]
