from hashlib import sha256
import json

from src.application.claim_extraction.claim_extraction_runtime import (
    ClaimExtractionRuntime,
)
from src.application.claim_extraction.models import (
    ClaimCandidate,
    ClaimExtractionResult,
)

from .models import (
    EntityCandidate,
    EntityEvidence,
    EntityExtractionPlan,
    EntityExtractionResult,
    EntityRecord,
)


class EntityExtractionRuntime:
    """Extracts deterministic entities from claim records and claim candidates."""

    STRATEGIES = (
        "STRUCTURED_METADATA_ENTITY",
        "CLAIM_PATTERN_ENTITY",
        "TITLE_ENTITY",
    )
    ENTITY_TYPES = (
        "PERSON",
        "ORGANIZATION",
        "LOCATION",
        "DATE",
        "WORK",
    )
    STRUCTURED_FIELDS = {
        "author": "PERSON",
        "creator": "PERSON",
        "publisher": "ORGANIZATION",
        "organization": "ORGANIZATION",
        "location": "LOCATION",
        "date": "DATE",
    }

    def __init__(self, claim_extraction_runtime):
        if not isinstance(claim_extraction_runtime, ClaimExtractionRuntime):
            raise TypeError(
                "EntityExtractionRuntime requires a ClaimExtractionRuntime"
            )
        self.claim_extraction_runtime = claim_extraction_runtime

    def execute_entity_extraction(self, plan, claim_extraction_result):
        self.validate_runtime_inputs_or_raise(plan, claim_extraction_result)
        candidates = self.generate_candidates(plan, claim_extraction_result)
        entities = self.build_entity_records(candidates, claim_extraction_result)
        entities = entities[: plan.entity_limit]
        result = self.build_extraction_result(plan, candidates, entities)
        if not self.validate_extraction(plan, claim_extraction_result, result):
            raise ValueError("Invalid entity extraction result")
        return result

    def extract_entities(self, plan, claim_extraction_result):
        return self.execute_entity_extraction(plan, claim_extraction_result)

    def generate_candidates(self, plan, claim_extraction_result):
        candidates = []
        candidates_by_text = {}
        for candidate in claim_extraction_result.candidates:
            candidates_by_text.setdefault(candidate.claim_text, []).append(candidate)
        for claim in sorted(
            claim_extraction_result.claims,
            key=lambda item: item.claim_id,
        ):
            source_candidates = candidates_by_text.get(claim.claim_text, [])
            source_strategies = {
                candidate.extraction_strategy for candidate in source_candidates
            }
            for strategy in plan.extraction_strategies:
                extracted = self._entities_for_strategy(
                    claim.claim_text,
                    strategy,
                    source_strategies,
                )
                for entity_name, entity_type in extracted:
                    entity_name = entity_name.strip()
                    if not entity_name or entity_type not in self.ENTITY_TYPES:
                        continue
                    candidate_id = self._candidate_id(
                        claim.claim_id,
                        entity_name,
                        entity_type,
                        strategy,
                    )
                    candidates.append(
                        EntityCandidate(
                            candidate_id=candidate_id,
                            source_claim_id=claim.claim_id,
                            entity_name=entity_name,
                            entity_type=entity_type,
                            extraction_strategy=strategy,
                        )
                    )
        return candidates

    def generate_entity_candidates(self, plan, claim_extraction_result):
        return self.generate_candidates(plan, claim_extraction_result)

    def build_entity_records(self, candidates, claim_extraction_result):
        claim_text_by_id = {
            claim.claim_id: claim.claim_text
            for claim in claim_extraction_result.claims
        }
        grouped = {}
        for candidate in candidates:
            grouped.setdefault(
                (candidate.entity_name, candidate.entity_type),
                [],
            ).append(candidate)
        entities = []
        for (entity_name, entity_type), entity_candidates in grouped.items():
            source_claim_ids = sorted(
                {candidate.source_claim_id for candidate in entity_candidates}
            )
            evidence = [
                self.generate_evidence(
                    claim_id,
                    claim_text_by_id[claim_id],
                )
                for claim_id in source_claim_ids
            ]
            entities.append(
                EntityRecord(
                    entity_id=self._entity_id(
                        entity_name,
                        entity_type,
                        source_claim_ids,
                    ),
                    entity_name=entity_name,
                    entity_type=entity_type,
                    source_claim_ids=source_claim_ids,
                    evidence=evidence,
                )
            )
        return entities

    def generate_evidence(self, claim_id, supporting_text):
        if not isinstance(claim_id, str) or not claim_id:
            raise ValueError("claim_id is required")
        if not isinstance(supporting_text, str) or not supporting_text.strip():
            raise ValueError("supporting_text is required")
        return EntityEvidence(
            evidence_id=self._evidence_id(claim_id, supporting_text),
            claim_id=claim_id,
            supporting_text=supporting_text,
        )

    def build_extraction_result(self, plan, candidates, entities):
        material = {
            "plan_id": plan.plan_id,
            "candidate_ids": [candidate.candidate_id for candidate in candidates],
            "entity_ids": [entity.entity_id for entity in entities],
        }
        result_id = (
            f"entity_extraction_result_"
            f"{sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode('utf-8')).hexdigest()[:16]}"
        )
        return EntityExtractionResult(
            result_id=result_id,
            plan_id=plan.plan_id,
            candidates=list(candidates),
            entities=list(entities),
            candidate_count=len(candidates),
            entity_count=len(entities),
        )

    def validate_extraction(self, plan, claim_extraction_result, extraction_result):
        if not self._validate_plan(plan):
            return False
        if not self._validate_claim_result(plan, claim_extraction_result):
            return False
        if not isinstance(extraction_result, EntityExtractionResult):
            return False
        if extraction_result.plan_id != plan.plan_id:
            return False
        if extraction_result.candidate_count != len(extraction_result.candidates):
            return False
        if extraction_result.entity_count != len(extraction_result.entities):
            return False
        if extraction_result.entity_count > plan.entity_limit:
            return False
        claim_ids = {
            claim.claim_id for claim in claim_extraction_result.claims
        }
        candidate_ids = [candidate.candidate_id for candidate in extraction_result.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            return False
        if any(
            not candidate.entity_name.strip()
            or candidate.entity_type not in self.ENTITY_TYPES
            or candidate.source_claim_id not in claim_ids
            or candidate.extraction_strategy not in self.STRATEGIES
            for candidate in extraction_result.candidates
        ):
            return False
        entity_ids = [entity.entity_id for entity in extraction_result.entities]
        entity_keys = [
            (entity.entity_name, entity.entity_type)
            for entity in extraction_result.entities
        ]
        if len(entity_ids) != len(set(entity_ids)):
            return False
        if len(entity_keys) != len(set(entity_keys)):
            return False
        if any(
            not entity.entity_name.strip()
            or entity.entity_type not in self.ENTITY_TYPES
            or not entity.source_claim_ids
            or entity.source_claim_ids != sorted(set(entity.source_claim_ids))
            or any(claim_id not in claim_ids for claim_id in entity.source_claim_ids)
            or not entity.evidence
            or entity.entity_id
            != self._entity_id(
                entity.entity_name,
                entity.entity_type,
                entity.source_claim_ids,
            )
            or any(
                evidence.claim_id not in entity.source_claim_ids
                or not evidence.supporting_text.strip()
                or evidence.evidence_id
                != self._evidence_id(
                    evidence.claim_id,
                    evidence.supporting_text,
                )
                for evidence in entity.evidence
            )
            for entity in extraction_result.entities
        ):
            return False
        return True

    def validate_runtime_inputs_or_raise(self, plan, claim_extraction_result):
        if not self._validate_plan(plan):
            raise ValueError("Invalid entity extraction plan")
        if not self._validate_claim_result(plan, claim_extraction_result):
            raise ValueError("Invalid claim extraction result")

    @classmethod
    def _entities_for_strategy(cls, claim_text, strategy, source_strategies):
        if strategy == "TITLE_ENTITY":
            if "TITLE_DERIVED" in source_strategies:
                return [(claim_text, "WORK")]
            return []
        if strategy == "STRUCTURED_METADATA_ENTITY":
            if "STRUCTURED_METADATA" not in source_strategies:
                return []
            return cls._parse_claim_pattern(claim_text, structured_only=True)
        if strategy == "CLAIM_PATTERN_ENTITY":
            if not source_strategies:
                return []
            return cls._parse_claim_pattern(claim_text, structured_only=False)
        return []

    @classmethod
    def _parse_claim_pattern(cls, claim_text, structured_only):
        if " is " not in claim_text:
            return []
        field, value = claim_text.split(" is ", 1)
        field = field.strip().lower().replace(" ", "_")
        value = value.strip()
        if not value:
            return []
        entity_type = cls.STRUCTURED_FIELDS.get(field)
        if entity_type is None:
            return []
        return [(value, entity_type)]

    def _validate_plan(self, plan):
        return (
            isinstance(plan, EntityExtractionPlan)
            and bool(plan.plan_id)
            and bool(plan.claim_extraction_result_id)
            and isinstance(plan.extraction_strategies, list)
            and bool(plan.extraction_strategies)
            and len(plan.extraction_strategies) == len(set(plan.extraction_strategies))
            and all(strategy in self.STRATEGIES for strategy in plan.extraction_strategies)
            and isinstance(plan.entity_limit, int)
            and not isinstance(plan.entity_limit, bool)
            and plan.entity_limit > 0
        )

    @staticmethod
    def _validate_claim_result(plan, claim_extraction_result):
        if not isinstance(claim_extraction_result, ClaimExtractionResult):
            return False
        if plan.claim_extraction_result_id != claim_extraction_result.result_id:
            return False
        if claim_extraction_result.claim_count != len(claim_extraction_result.claims):
            return False
        if claim_extraction_result.candidate_count != len(claim_extraction_result.candidates):
            return False
        claim_ids = [claim.claim_id for claim in claim_extraction_result.claims]
        if len(claim_ids) != len(set(claim_ids)):
            return False
        return all(claim.claim_text.strip() for claim in claim_extraction_result.claims)

    @staticmethod
    def _candidate_id(claim_id, entity_name, entity_type, strategy):
        material = "\x00".join([claim_id, entity_name, entity_type, strategy])
        return f"entity_candidate_{sha256(material.encode('utf-8')).hexdigest()[:16]}"

    @staticmethod
    def _evidence_id(claim_id, supporting_text):
        material = "\x00".join([claim_id, supporting_text])
        return f"entity_evidence_{sha256(material.encode('utf-8')).hexdigest()[:16]}"

    @staticmethod
    def _entity_id(entity_name, entity_type, source_claim_ids):
        material = "\x00".join([entity_name, entity_type, *source_claim_ids])
        return f"entity_{sha256(material.encode('utf-8')).hexdigest()[:16]}"


__all__ = ["EntityExtractionRuntime"]
