from dataclasses import dataclass, field
@dataclass
class ContradictionCandidate: candidate_id: str; subject: str; predicate: str; values: list[str] = field(default_factory=list); claim_ids: list[str] = field(default_factory=list)
@dataclass
class ContradictionRecord: contradiction_id: str; subject: str; predicate: str; values: list[str] = field(default_factory=list); claim_ids: list[str] = field(default_factory=list)
@dataclass
class ContradictionResult: result_id: str; contradictions: list[ContradictionRecord] = field(default_factory=list); contradiction_count: int = 0
