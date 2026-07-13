from pathlib import Path

from .repository_serializer import RepositorySerializer


class PersistentKnowledgeRepository:
    """Durable storage and ID-based merge boundary for canonical knowledge graphs."""

    def __init__(self, path, serializer=None):
        self.path = Path(path)
        self.serializer = serializer or RepositorySerializer()

    def exists(self, object_id=None):
        if object_id is None:
            return (self.path / self.serializer.GRAPH_FILE).exists()
        return self.get_by_id(object_id) is not None

    def load(self):
        return self.serializer.load(self.path)

    def save(self, graph):
        self.serializer.save(self.path, graph)
        return graph

    def merge(self, graph):
        return self.serializer.merge(self.load(), graph)

    def get_by_id(self, object_id):
        graph = self.load()
        node = graph.get_node(object_id)
        if node is not None:
            return node
        return next(
            (edge for edge in graph.edges if edge.relationship_id == object_id),
            None,
        )


__all__ = ["PersistentKnowledgeRepository"]
