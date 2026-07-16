from src.application.knowledge.graph_builder import GraphBuilder
from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.knowledge_v2.pipeline import KnowledgeExtractionPipeline


def test_knowledge_repository_uses_the_canonical_extraction_and_graph_builders():
    repository = KnowledgeRepository()

    assert type(repository.extractor) is KnowledgeExtractionPipeline
    assert type(repository.graph_builder) is GraphBuilder
