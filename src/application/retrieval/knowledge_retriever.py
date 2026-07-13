from src.application.knowledge.canonicalizer import Canonicalizer

from .retrieval_index import RetrievalIndex


class KnowledgeRetriever:
    """Canonical read-only query API for a loaded knowledge graph."""

    ENTITY_TYPES = {"PERSON", "ORGANIZATION", "LOCATION", "EVENT", "ENTITY"}

    def __init__(self, graph):
        self._graph = graph
        self.index = RetrievalIndex(graph)

    @classmethod
    def from_repository(cls, repository):
        return cls(repository.load())

    @classmethod
    def load_repository(cls, path):
        from src.application.repository.persistent_knowledge_repository import (
            PersistentKnowledgeRepository,
        )

        return cls.from_repository(PersistentKnowledgeRepository(path))

    def find(self, identifier):
        return self.lookup(identifier)

    def lookup(self, identifier):
        return self.find_node(identifier) or self.index.edges_by_id.get(identifier)

    def find_node(self, node_id):
        return self.index.nodes_by_id.get(node_id)

    def find_claim(self, claim_id):
        return self.index.claims_by_id.get(claim_id)

    def find_source(self, source_id):
        return self.index.sources_by_id.get(source_id)

    def find_document(self, document_id):
        return self.index.documents_by_id.get(document_id)

    def find_evidence(self, evidence_id):
        return self.index.evidence_by_id.get(evidence_id)

    def find_entities(self, name):
        return self._find_named(name, self.ENTITY_TYPES)

    def find_entity(self, name):
        matches = self.find_entities(name)
        return matches[0] if matches else None

    def find_people(self, name):
        return self._find_named(name, {"PERSON"})

    def find_locations(self, name):
        return self._find_named(name, {"LOCATION"})

    def find_events(self, name):
        return self._find_named(name, {"EVENT"})

    def get_outgoing(self, node_id):
        return list(self.index.outgoing_by_node_id.get(node_id, []))

    def get_incoming(self, node_id):
        return list(self.index.incoming_by_node_id.get(node_id, []))

    def get_relationships(self, node_id):
        relationships = self.get_outgoing(node_id) + self.get_incoming(node_id)
        return self._unique_edges(relationships)

    def get_neighbors(self, node_id):
        neighbors = []
        for edge in self.get_relationships(node_id):
            neighbor_id = edge.target if edge.source == node_id else edge.source
            node = self.find_node(neighbor_id)
            if node is not None:
                neighbors.append(node)
        return self._unique_nodes(neighbors)

    def traverse(self, node_id):
        return {
            "node": self.find_node(node_id),
            "incoming": self.get_incoming(node_id),
            "outgoing": self.get_outgoing(node_id),
            "neighbors": self.get_neighbors(node_id),
        }

    def get_claim_evidence(self, claim_id):
        claim = self.find_claim(claim_id)
        if claim is None:
            return []
        data = claim.data if isinstance(claim.data, dict) else {}
        evidence_ids = data.get("evidence_ids", [])
        evidence = [self.find_evidence(evidence_id) for evidence_id in evidence_ids]
        evidence = [node for node in evidence if node is not None]
        if evidence:
            return evidence
        return [
            self.find_evidence(edge.target)
            for edge in self.get_outgoing(claim.id)
            if edge.relation == "supported_by" and self.find_evidence(edge.target) is not None
        ]

    def get_claim_sources(self, claim_id):
        claim = self.find_claim(claim_id)
        if claim is None:
            return []
        data = claim.data if isinstance(claim.data, dict) else {}
        source_ids = data.get("source_ids", [])
        sources = [self.find_source(source_id) for source_id in source_ids]
        sources = [node for node in sources if node is not None]
        if sources:
            return self._unique_nodes(sources)
        return [
            self.find_source(edge.target)
            for edge in self.get_outgoing(claim.id)
            if edge.relation == "attributed_to" and self.find_source(edge.target) is not None
        ]

    def get_evidence_document(self, evidence_id):
        evidence = self.find_evidence(evidence_id)
        if evidence is None:
            return None
        data = evidence.data if isinstance(evidence.data, dict) else {}
        document = self.find_document(data.get("document_id", ""))
        if document is not None:
            return document
        return next(
            (
                self.find_document(edge.target)
                for edge in self.get_outgoing(evidence.id)
                if edge.relation == "located_in" and self.find_document(edge.target) is not None
            ),
            None,
        )

    def get_document_source(self, document_id):
        document = self.find_document(document_id)
        if document is None:
            return None
        data = document.data if isinstance(document.data, dict) else {}
        source = self.find_source(data.get("source_id", ""))
        if source is not None:
            return source
        return next(
            (
                self.find_source(edge.target)
                for edge in self.get_outgoing(document.id)
                if edge.relation == "originates_from" and self.find_source(edge.target) is not None
            ),
            None,
        )

    def get_claim_provenance(self, claim_id):
        claim = self.find_claim(claim_id)
        evidence = self.get_claim_evidence(claim_id)
        documents = self._unique_nodes(
            [document for item in evidence if (document := self.get_evidence_document(item.id))]
        )
        sources = self._unique_nodes(
            self.get_claim_sources(claim_id)
            + [source for item in documents if (source := self.get_document_source(item.id))]
        )
        return {
            "claim": claim,
            "evidence": evidence,
            "documents": documents,
            "sources": sources,
        }

    provenance = get_claim_provenance

    def _find_named(self, name, node_types):
        normalized_name = Canonicalizer.normalize_text(name)
        matches = []
        for node_type in node_types:
            for node in self.index.nodes_by_type.get(node_type, []):
                data = node.data if isinstance(node.data, dict) else {}
                values = [node.id, data.get("name", ""), data.get("title", "")]
                if any(Canonicalizer.normalize_text(value) == normalized_name for value in values):
                    matches.append(node)
        return self._unique_nodes(matches)

    @staticmethod
    def _unique_nodes(nodes):
        seen = set()
        result = []
        for node in nodes:
            if node.id not in seen:
                seen.add(node.id)
                result.append(node)
        return result

    @staticmethod
    def _unique_edges(edges):
        seen = set()
        result = []
        for edge in edges:
            if edge.relationship_id not in seen:
                seen.add(edge.relationship_id)
                result.append(edge)
        return result


__all__ = ["KnowledgeRetriever"]
