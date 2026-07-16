import re
from hashlib import sha256

from src.application.knowledge.canonicalizer import Canonicalizer
from src.application.retrieval.knowledge_retriever import KnowledgeRetriever

from .models import ClaimCluster, ContradictionRecord, SupportProfile


class HistoricalReasoner:
    """Deterministic, read-only analysis of claims retrieved from knowledge storage."""

    _NUMBER_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\b")
    _TITLE_PATTERN = re.compile(r"\b(?:the )?prophet muhammad\b")

    def __init__(self, retriever):
        if not isinstance(retriever, KnowledgeRetriever):
            raise TypeError("HistoricalReasoner requires a KnowledgeRetriever")
        self.retriever = retriever

    def analyze_claim(self, claim_id):
        claim = self.retriever.find_claim(claim_id)
        return {
            "claim": claim,
            "cluster": self.build_claim_cluster(claim_id) if claim else None,
            "support_profile": self.get_support_profile(claim_id) if claim else None,
            "contradictions": self.find_contradictions(claim_id),
        }

    def get_claims(self):
        return self.retriever.get_claims()

    def get_claim(self, claim_id):
        return self.retriever.find_claim(claim_id)

    def get_claim_provenance(self, claim_id):
        return self.retriever.get_claim_provenance(claim_id)

    def find_related_claims(self, claim_id):
        claim = self.retriever.find_claim(claim_id)
        if claim is None:
            return []

        related = []
        target_text = self._normalized_claim_text(claim)
        target_evidence = {item.id for item in self.retriever.get_claim_evidence(claim_id)}
        target_sources = {item.id for item in self.retriever.get_claim_sources(claim_id)}

        for candidate in self.retriever.get_claims():
            if candidate.id == claim_id:
                continue
            candidate_evidence = {
                item.id for item in self.retriever.get_claim_evidence(candidate.id)
            }
            candidate_sources = {
                item.id for item in self.retriever.get_claim_sources(candidate.id)
            }
            if (
                self._normalized_claim_text(candidate) == target_text
                or target_evidence.intersection(candidate_evidence)
                or target_sources.intersection(candidate_sources)
            ):
                related.append(candidate)
        return related

    def build_claim_cluster(self, claim_id):
        claim = self.retriever.find_claim(claim_id)
        if claim is None:
            return None

        claim_ids = {claim.id}
        pending = [claim.id]
        while pending:
            current_id = pending.pop()
            for related in self.find_related_claims(current_id):
                if related.id not in claim_ids:
                    claim_ids.add(related.id)
                    pending.append(related.id)

        evidence_ids = set()
        document_ids = set()
        source_ids = set()
        for clustered_claim_id in claim_ids:
            evidence = self.retriever.get_claim_evidence(clustered_claim_id)
            sources = self.retriever.get_claim_sources(clustered_claim_id)
            evidence_ids.update(item.id for item in evidence)
            source_ids.update(item.id for item in sources)
            for item in evidence:
                document = self.retriever.get_evidence_document(item.id)
                if document is not None:
                    document_ids.add(document.id)
                    source = self.retriever.get_document_source(document.id)
                    if source is not None:
                        source_ids.add(source.id)

        ordered_claim_ids = sorted(claim_ids)
        cluster_key = "\x00".join(ordered_claim_ids)
        return ClaimCluster(
            cluster_id=f"cluster_{sha256(cluster_key.encode('utf-8')).hexdigest()[:16]}",
            claim_ids=ordered_claim_ids,
            evidence_ids=sorted(evidence_ids),
            document_ids=sorted(document_ids),
            source_ids=sorted(source_ids),
        )

    def get_support_profile(self, claim_id):
        claim = self.retriever.find_claim(claim_id)
        if claim is None:
            return None

        evidence = self.retriever.get_claim_evidence(claim_id)
        sources = {item.id for item in self.retriever.get_claim_sources(claim_id)}
        documents = set()
        for item in evidence:
            document = self.retriever.get_evidence_document(item.id)
            if document is not None:
                documents.add(document.id)
                source = self.retriever.get_document_source(document.id)
                if source is not None:
                    sources.add(source.id)

        data = claim.data if isinstance(claim.data, dict) else {}
        extraction_confidence = float(data.get("confidence", 1.0))
        evidence_count = len({item.id for item in evidence})
        source_count = len(sources)
        document_count = len(documents)
        confidence_score = round(
            min(
                1.0,
                extraction_confidence * 0.6
                + min(evidence_count, 2) * 0.1
                + min(source_count, 2) * 0.1
                + min(document_count, 2) * 0.1,
            ),
            2,
        )
        return SupportProfile(
            claim_id=claim_id,
            evidence_count=evidence_count,
            source_count=source_count,
            document_count=document_count,
            confidence_score=confidence_score,
            confidence_signals=[
                f"extraction_confidence={extraction_confidence:.2f}",
                f"evidence_count={evidence_count}",
                f"source_count={source_count}",
                f"document_count={document_count}",
            ],
        )

    def find_contradictions(self, claim_id=None):
        claims = self.retriever.get_claims()
        if claim_id is not None:
            claim = self.retriever.find_claim(claim_id)
            if claim is None:
                return []
            candidates = [claim]
        else:
            candidates = claims

        contradictions = []
        seen_pairs = set()
        for claim_a in candidates:
            signature_a, numbers_a = self._numeric_signature(claim_a)
            if not numbers_a:
                continue
            for claim_b in claims:
                if claim_a.id == claim_b.id:
                    continue
                pair = tuple(sorted((claim_a.id, claim_b.id)))
                if pair in seen_pairs:
                    continue
                signature_b, numbers_b = self._numeric_signature(claim_b)
                if signature_a != signature_b or not numbers_b or numbers_a == numbers_b:
                    continue
                seen_pairs.add(pair)
                contradictions.append(
                    ContradictionRecord(
                        claim_a=pair[0],
                        claim_b=pair[1],
                        reason=f"conflicting numeric values for claim pattern: {signature_a}",
                        confidence=0.75,
                    )
                )
        return contradictions

    def _normalized_claim_text(self, claim):
        data = claim.data if isinstance(claim.data, dict) else {}
        text = Canonicalizer.normalize_text(data.get("text", ""))
        return self._TITLE_PATTERN.sub("muhammad", text)

    def _numeric_signature(self, claim):
        text = self._normalized_claim_text(claim)
        numbers = tuple(self._NUMBER_PATTERN.findall(text))
        return self._NUMBER_PATTERN.sub("{number}", text), numbers


__all__ = ["HistoricalReasoner"]
