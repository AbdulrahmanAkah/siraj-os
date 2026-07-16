from hashlib import sha256
import json

from src.application.knowledge_repository.models import KnowledgeRecord
from src.application.retrieval.models import RetrievalResult
from src.application.retrieval.retrieval_runtime_engine import (
    RetrievalRuntimeEngine,
)

from .models import (
    ClaimCandidate,
    ClaimEvidence,
    ClaimExtractionPlan,
    ClaimExtractionResult,
    ClaimRecord,
)


class ClaimExtractionRuntime:
    """Extracts deterministic claims from retrieval-result record metadata only."""

    STRATEGIES = (
        "EXPLICIT_STATEMENT",
        "STRUCTURED_METADATA",
        "TITLE_DERIVED",
    )
    EXPLICIT_FIELDS = ("title", "summary", "description", "caption")

    def __init__(self, retrieval_runtime_engine):
        if not isinstance(retrieval_runtime_engine, RetrievalRuntimeEngine):
            raise TypeError(
                "ClaimExtractionRuntime requires a RetrievalRuntimeEngine"
            )
        self.retrieval_runtime_engine = retrieval_runtime_engine

    def execute_claim_extraction(self, plan, retrieval_result):
        self.validate_runtime_inputs_or_raise(plan, retrieval_result)
        candidates = self.generate_candidates(plan, retrieval_result)
        claims = self.build_claim_records(candidates, retrieval_result)
        claims = claims[: plan.claim_limit]
        result = self.build_extraction_result(
            plan,
            candidates,
            claims,
        )
        if not self.validate_extraction(plan, retrieval_result, result):
            raise ValueError("Invalid claim extraction result")
        return result

    def extract_claims(self, plan, retrieval_result):
        return self.execute_claim_extraction(plan, retrieval_result)

    def generate_candidates(self, plan, retrieval_result):
        candidates = []
        for match in sorted(
            retrieval_result.matches,
            key=lambda item: item.record_id,
        ):
            record = match.record
            for strategy in plan.extraction_strategies:
                for claim_text in self._texts_for_strategy(record, strategy):
                    claim_text = claim_text.strip()
                    if not claim_text:
                        continue
                    candidate_id = self._candidate_id(
                        match.record_id,
                        claim_text,
                        strategy,
                    )
                    candidates.append(
                        ClaimCandidate(
                            candidate_id=candidate_id,
                            source_record_id=match.record_id,
                            claim_text=claim_text,
                            extraction_strategy=strategy,
                        )
                    )
        return candidates

    def generate_claim_candidates(self, plan, retrieval_result):
        return self.generate_candidates(plan, retrieval_result)

    def build_claim_records(self, candidates, retrieval_result):
        records_by_id = {
            match.record_id: match.record
            for match in retrieval_result.matches
        }
        grouped = {}
        for candidate in candidates:
            grouped.setdefault(candidate.claim_text, []).append(candidate)
        claims = []
        for claim_text, claim_candidates in grouped.items():
            source_record_ids = sorted(
                {candidate.source_record_id for candidate in claim_candidates}
            )
            evidence = []
            for record_id in source_record_ids:
                record = records_by_id[record_id]
                evidence.append(
                    self.generate_evidence(
                        record,
                        claim_text,
                    )
                )
            claim_id = self._claim_id(claim_text, source_record_ids)
            claims.append(
                ClaimRecord(
                    claim_id=claim_id,
                    claim_text=claim_text,
                    evidence=evidence,
                    source_record_ids=source_record_ids,
                )
            )
        return claims

    def generate_evidence(self, record, supporting_text):
        if not isinstance(record, KnowledgeRecord):
            raise TypeError("record must be a KnowledgeRecord")
        evidence_id = self._evidence_id(
            record.record_id,
            record.fingerprint,
            supporting_text,
        )
        return ClaimEvidence(
            evidence_id=evidence_id,
            record_id=record.record_id,
            fingerprint=record.fingerprint,
            supporting_text=supporting_text,
        )

    def build_extraction_result(self, plan, candidates, claims):
        material = {
            "plan_id": plan.plan_id,
            "candidate_ids": [candidate.candidate_id for candidate in candidates],
            "claim_ids": [claim.claim_id for claim in claims],
        }
        result_id = (
            f"claim_extraction_result_"
            f"{sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode('utf-8')).hexdigest()[:16]}"
        )
        return ClaimExtractionResult(
            result_id=result_id,
            plan_id=plan.plan_id,
            claims=list(claims),
            candidates=list(candidates),
            claim_count=len(claims),
            candidate_count=len(candidates),
        )

    def validate_extraction(self, plan, retrieval_result, extraction_result):
        if not self._validate_plan(plan):
            return False
        if not self._validate_retrieval_result(plan, retrieval_result):
            return False
        if not isinstance(extraction_result, ClaimExtractionResult):
            return False
        if extraction_result.plan_id != plan.plan_id:
            return False
        if extraction_result.candidate_count != len(extraction_result.candidates):
            return False
        if extraction_result.claim_count != len(extraction_result.claims):
            return False
        if extraction_result.claim_count > plan.claim_limit:
            return False
        records_by_id = {
            match.record_id: match.record
            for match in retrieval_result.matches
        }
        candidate_ids = [candidate.candidate_id for candidate in extraction_result.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            return False
        if any(
            not candidate.claim_text.strip()
            or candidate.source_record_id not in records_by_id
            or candidate.extraction_strategy not in self.STRATEGIES
            for candidate in extraction_result.candidates
        ):
            return False
        claim_ids = [claim.claim_id for claim in extraction_result.claims]
        claim_texts = [claim.claim_text for claim in extraction_result.claims]
        if len(claim_ids) != len(set(claim_ids)):
            return False
        if len(claim_texts) != len(set(claim_texts)):
            return False
        if any(
            not claim.claim_text.strip()
            or not claim.evidence
            or claim.source_record_ids != sorted(set(claim.source_record_ids))
            or not claim.source_record_ids
            or any(record_id not in records_by_id for record_id in claim.source_record_ids)
            or claim.claim_id != self._claim_id(
                claim.claim_text,
                claim.source_record_ids,
            )
            or any(
                evidence.record_id not in records_by_id
                or not evidence.supporting_text.strip()
                or evidence.fingerprint
                != records_by_id[evidence.record_id].fingerprint
                or evidence.evidence_id
                != self._evidence_id(
                    evidence.record_id,
                    evidence.fingerprint,
                    evidence.supporting_text,
                )
                for evidence in claim.evidence
            )
            for claim in extraction_result.claims
        ):
            return False
        return True

    def validate_runtime_inputs_or_raise(self, plan, retrieval_result):
        if not self._validate_plan(plan):
            raise ValueError("Invalid claim extraction plan")
        if not self._validate_retrieval_result(plan, retrieval_result):
            raise ValueError("Invalid retrieval result")

    @staticmethod
    def _texts_for_strategy(record, strategy):
        if strategy == "EXPLICIT_STATEMENT":
            return [
                record.metadata[field]
                for field in ClaimExtractionRuntime.EXPLICIT_FIELDS
                if field in record.metadata
            ]
        if strategy == "STRUCTURED_METADATA":
            return [
                f"{key.replace('_', ' ').title()} is {value}"
                for key, value in sorted(record.metadata.items())
            ]
        if strategy == "TITLE_DERIVED":
            return [record.metadata["title"]] if "title" in record.metadata else []
        return []

    def _validate_plan(self, plan):
        return (
            isinstance(plan, ClaimExtractionPlan)
            and isinstance(plan.plan_id, str)
            and bool(plan.plan_id)
            and isinstance(plan.retrieval_id, str)
            and bool(plan.retrieval_id)
            and isinstance(plan.extraction_strategies, list)
            and bool(plan.extraction_strategies)
            and len(plan.extraction_strategies)
            == len(set(plan.extraction_strategies))
            and all(strategy in self.STRATEGIES for strategy in plan.extraction_strategies)
            and isinstance(plan.claim_limit, int)
            and not isinstance(plan.claim_limit, bool)
            and plan.claim_limit > 0
        )

    @staticmethod
    def _validate_retrieval_result(plan, retrieval_result):
        if not isinstance(retrieval_result, RetrievalResult):
            return False
        if plan.retrieval_id != retrieval_result.retrieval_id:
            return False
        if retrieval_result.match_count != len(retrieval_result.matches):
            return False
        record_ids = [match.record_id for match in retrieval_result.matches]
        if record_ids != sorted(record_ids) or len(record_ids) != len(set(record_ids)):
            return False
        return all(
            isinstance(match.record, KnowledgeRecord)
            and match.record_id == match.record.record_id
            for match in retrieval_result.matches
        )

    @staticmethod
    def _candidate_id(record_id, claim_text, strategy):
        material = "\x00".join([record_id, strategy, claim_text])
        return (
            f"claim_candidate_"
            f"{sha256(material.encode('utf-8')).hexdigest()[:16]}"
        )

    @staticmethod
    def _evidence_id(record_id, fingerprint, supporting_text):
        material = "\x00".join([record_id, fingerprint, supporting_text])
        return (
            f"claim_evidence_"
            f"{sha256(material.encode('utf-8')).hexdigest()[:16]}"
        )

    @staticmethod
    def _claim_id(claim_text, source_record_ids):
        material = "\x00".join([claim_text, *source_record_ids])
        return f"claim_{sha256(material.encode('utf-8')).hexdigest()[:16]}"


__all__ = ["ClaimExtractionRuntime"]
