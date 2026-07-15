from hashlib import sha256
import json
import re

from src.application.claim_extraction.models import ClaimExtractionResult
from src.application.historical_reasoning_foundation.models import ReasoningResult

from .models import (
    CausalCandidate,
    CausalReasoningPlan,
    CausalReasoningResult,
    CausalRelation,
)


class CausalReasoningRuntime:
    PATTERN = re.compile(
        r"^(?P<cause>.+?)\s+(?P<relation>CAUSES|CONTRIBUTES_TO|PRECEDES_CAUSE)\s+(?P<effect>.+?)$"
    )

    def build_causal_result(self, plan, claims, reasoning):
        if not self._valid_inputs(plan, claims, reasoning):
            raise ValueError("Invalid causal reasoning inputs")
        candidates = self.generate_candidates(plan, claims, reasoning)
        grouped = {}
        for candidate in candidates:
            key = (
                candidate.relation_type,
                candidate.cause_text,
                candidate.effect_text,
            )
            grouped.setdefault(key, []).append(candidate)
        relations = []
        for position, key in enumerate(sorted(grouped)):
            group = grouped[key]
            relation_type, cause_text, effect_text = key
            claim_ids = sorted({item.source_claim_id for item in group})
            evidence_ids = sorted(
                {evidence_id for item in group for evidence_id in item.evidence_ids}
            )
            relations.append(
                CausalRelation(
                    relation_id=self._id(
                        "causal_relation",
                        [relation_type, cause_text, effect_text, claim_ids, evidence_ids],
                    ),
                    relation_type=relation_type,
                    cause_text=cause_text,
                    effect_text=effect_text,
                    source_claim_ids=claim_ids,
                    evidence_ids=evidence_ids,
                    position=position,
                )
            )
        result = CausalReasoningResult(
            result_id=self._id(
                "causal_reasoning_result",
                [plan.plan_id, *[item.relation_id for item in relations], "VALID"],
            ),
            plan_id=plan.plan_id,
            candidates=candidates,
            relations=relations,
            relation_count=len(relations),
            validation_state="VALID",
        )
        if not self.validate_causal(plan, claims, reasoning, result):
            raise ValueError("Invalid causal reasoning result")
        return result

    def generate_candidates(self, plan, claims, reasoning):
        allowed_claim_ids = {
            claim_id
            for chain in reasoning.chains
            for candidate in chain.candidates
            for claim_id in candidate.source_claim_ids
        }
        candidates = []
        for claim in sorted(claims.claims, key=lambda item: item.claim_id):
            if claim.claim_id not in allowed_claim_ids:
                continue
            match = self.PATTERN.fullmatch(claim.claim_text)
            if match is None or match.group("relation") not in plan.allowed_relation_types:
                continue
            evidence_ids = sorted(item.evidence_id for item in claim.evidence)
            if not evidence_ids:
                continue
            material = [
                match.group("relation"),
                match.group("cause"),
                match.group("effect"),
                claim.claim_id,
                evidence_ids,
            ]
            candidates.append(
                CausalCandidate(
                    candidate_id=self._id("causal_candidate", material),
                    relation_type=match.group("relation"),
                    cause_text=match.group("cause"),
                    effect_text=match.group("effect"),
                    source_claim_id=claim.claim_id,
                    evidence_ids=evidence_ids,
                )
            )
        return sorted(candidates, key=lambda item: item.candidate_id)

    def validate_causal(self, plan, claims, reasoning, result):
        if not self._valid_inputs(plan, claims, reasoning):
            return False
        if not isinstance(result, CausalReasoningResult):
            return False
        if result.plan_id != plan.plan_id or result.validation_state != "VALID":
            return False
        if result.relation_count != len(result.relations):
            return False
        relation_ids = [item.relation_id for item in result.relations]
        if len(relation_ids) != len(set(relation_ids)):
            return False
        if [item.position for item in result.relations] != list(range(len(result.relations))):
            return False
        if any(
            item.relation_type not in plan.allowed_relation_types
            or not item.source_claim_ids
            or not item.evidence_ids
            for item in result.relations
        ):
            return False
        return result.candidates == self.generate_candidates(plan, claims, reasoning)

    @staticmethod
    def _valid_inputs(plan, claims, reasoning):
        return (
            isinstance(plan, CausalReasoningPlan)
            and bool(plan.plan_id)
            and isinstance(claims, ClaimExtractionResult)
            and claims.claim_count == len(claims.claims)
            and isinstance(reasoning, ReasoningResult)
            and reasoning.chain_count == len(reasoning.chains)
        )

    @staticmethod
    def _id(prefix, material):
        return prefix + "_" + sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]


__all__ = ["CausalReasoningRuntime"]
