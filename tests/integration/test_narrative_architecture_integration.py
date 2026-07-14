import pytest

from src.application.documentary_planning.documentary_planner import DocumentaryPlanner
from src.application.events.event_engine import EventEngine
from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.narrative_architecture.narrative_architect import NarrativeArchitect
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.script_architecture.script_architect import ScriptArchitect
from src.application.selection.claim_selector import ClaimSelector


def test_script_architect_requires_narrative_architect_and_does_not_mutate_graph():
    graph = KnowledgeRepository().ingest_text("Muhammad traveled to Makkah in 610.")
    before = graph.to_dict()
    narrative_architect = NarrativeArchitect(
        DocumentaryPlanner(
            EventEngine(ClaimSelector(HistoricalReasoner(KnowledgeRetriever(graph))))
        )
    )

    with pytest.raises(TypeError):
        ScriptArchitect(narrative_architect.documentary_planner)

    script_architect = ScriptArchitect(narrative_architect)
    architecture = narrative_architect.build_narrative_architecture()
    assert script_architect.validate_structure(
        script_architect.build_script_structure(architecture),
        architecture,
    )
    assert not hasattr(script_architect, "graph")
    assert graph.to_dict() == before
