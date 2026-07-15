from dataclasses import dataclass, field
@dataclass
class SourceProfile: source_id: str; source_type: str; evidence_count: int; contradiction_count: int
@dataclass
class SourceReliabilityScore: score_id: str; source_id: str; reliability: str; score: int
@dataclass
class ReliabilityResult: result_id: str; scores: list[SourceReliabilityScore] = field(default_factory=list); score_count: int = 0
