from src.application.events.event_engine import EventEngine
from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def _engine(text):
    graph = KnowledgeRepository().ingest_text(text)
    return EventEngine(ClaimSelector(HistoricalReasoner(KnowledgeRetriever(graph))))


def test_event_engine_builds_a_historical_event_from_a_selected_claim():
    engine = _engine("The Battle of Badr occurred in 624. The source is History Book.")
    claim = engine.selector.reasoner.get_claims()[0]

    event = engine.build_event(claim.id)

    assert event.event_id.startswith("event_")
    assert event.claim_ids == [claim.id]
    assert event.source_ids
    assert event.document_ids
    assert event.evidence_ids
    assert event.year == 624
    assert event.date is None
    assert event.confidence > 0
