from dataclasses import dataclass,field
@dataclass
class EvidenceWeight: weight_id:str; resolved_evidence_id:str; weight:int; level:str
@dataclass
class WeightedEvidence: resolved_evidence_id:str; weight:EvidenceWeight
@dataclass
class EvidenceWeightResult: result_id:str; weighted_evidence:list[WeightedEvidence]=field(default_factory=list); weight_count:int=0
