from .knowledge_retriever import KnowledgeRetriever
from .retrieval_index import RetrievalIndex as GraphRetrievalIndex

__all__ = [
    "GraphRetrievalIndex",
    "KnowledgeRetriever",
    "IndexEntry",
    "RetrievalIndex",
    "RetrievalIndexBuilder",
    "RetrievalMatch",
    "RetrievalRequest",
    "RetrievalResult",
    "RetrievalRuntimeEngine",
]


def __getattr__(name):
    if name in {
        "IndexEntry",
        "RetrievalIndex",
        "RetrievalMatch",
        "RetrievalRequest",
        "RetrievalResult",
    }:
        from . import models

        return getattr(models, name)
    if name == "RetrievalIndexBuilder":
        from .retrieval_index_builder import RetrievalIndexBuilder

        return RetrievalIndexBuilder
    if name == "RetrievalRuntimeEngine":
        from .retrieval_runtime_engine import RetrievalRuntimeEngine

        return RetrievalRuntimeEngine
    raise AttributeError(name)
