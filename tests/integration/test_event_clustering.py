from src.application.events.event_engine import EventEngine
from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.reasoning.historical_reasoner import HistoricalReasoner
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever
from src.application.selection.claim_selector import ClaimSelector


def test_multiple_clustered_claims_produce_one_historical_event():
    graph = KnowledgeRepository().ingest_text(
        "Battle of Badr occurred in 624. Muslims won the Battle of Badr. "
        "The battle took place near Medina. The source is History Book."
    )
    engine = EventEngine(ClaimSelector(HistoricalReasoner(KnowledgeRetriever(graph))))

    events = engine.build_events()

    assert len(events) == 1
    assert len(events[0].claim_ids) == 3
    assert events[0].year == 624
