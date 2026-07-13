from src.application.reasoning.historical_reasoner import HistoricalReasoner

from .models import ClaimScore, SelectionProfile


class ClaimSelector:
    """Deterministic, explainable claim selection over historical reasoning results."""

    REJECTION_THRESHOLD = 0.35
    CONTRADICTION_PENALTY = 0.30

    def __init__(self, reasoner):
        if not isinstance(reasoner, HistoricalReasoner):
            raise TypeError("ClaimSelector requires a HistoricalReasoner")
        self.reasoner = reasoner

    def evaluate_claim(self, claim_id):
        profile = self.reasoner.get_support_profile(claim_id)
        if profile is None:
            return None

        cluster = self.reasoner.build_claim_cluster(claim_id)
        contradictions = self.reasoner.find_contradictions(claim_id)
        support_score = round(profile.confidence_score * 0.30, 3)
        source_score = round(min(profile.source_count, 2) * 0.125, 3)
        evidence_score = round(min(profile.evidence_count, 2) * 0.125, 3)
        cluster_bonus = round(min(max(len(cluster.claim_ids) - 1, 0), 3) * 0.03, 3)
        contradiction_penalty = round(
            min(len(contradictions) * self.CONTRADICTION_PENALTY, 0.50),
            3,
        )
        score = round(
            max(
                0.0,
                support_score + source_score + evidence_score + cluster_bonus
                - contradiction_penalty,
            ),
            3,
        )
        return ClaimScore(
            claim_id=claim_id,
            score=score,
            support_score=support_score,
            source_score=source_score,
            evidence_score=evidence_score,
            contradiction_penalty=contradiction_penalty,
        )

    def rank_claims(self):
        scores = [
            score
            for claim in self.reasoner.get_claims()
            if (score := self.evaluate_claim(claim.id)) is not None
        ]
        return sorted(scores, key=lambda score: (-score.score, score.claim_id))

    def select_top_claims(self, limit=50):
        return self.rank_claims()[:max(0, limit)]

    def select_claims(self, limit=50):
        return self.select_top_claims(limit)

    def reject_claims(self):
        return [
            score
            for score in self.rank_claims()
            if score.score < self.REJECTION_THRESHOLD
        ]

    def build_selection_profile(self, claim_id):
        score = self.evaluate_claim(claim_id)
        profile = self.reasoner.get_support_profile(claim_id)
        if score is None or profile is None:
            return None

        cluster = self.reasoner.build_claim_cluster(claim_id)
        contradictions = self.reasoner.find_contradictions(claim_id)
        reasons = [
            f"support confidence contribution={score.support_score:.3f}",
            f"evidence contribution={score.evidence_score:.3f}",
            f"source contribution={score.source_score:.3f}",
        ]
        if len(cluster.claim_ids) > 1:
            reasons.append(f"cluster bonus for {len(cluster.claim_ids)} related claims")
        if contradictions:
            reasons.append(
                f"contradiction penalty={score.contradiction_penalty:.3f}"
            )
        if score.score < self.REJECTION_THRESHOLD:
            reasons.append("below deterministic rejection threshold")

        return SelectionProfile(
            claim_id=claim_id,
            final_score=score.score,
            reasons=reasons,
            support_summary=(
                f"evidence={profile.evidence_count}, sources={profile.source_count}, "
                f"documents={profile.document_count}"
            ),
            contradiction_summary=(
                f"potential_contradictions={len(contradictions)}"
                if contradictions
                else "potential_contradictions=0"
            ),
        )


__all__ = ["ClaimSelector"]
