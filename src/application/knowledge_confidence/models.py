from dataclasses import dataclass,field
@dataclass
class ConfidenceRecord: confidence_id:str; subject_id:str; confidence:str
@dataclass
class ConfidenceAssessment: assessment_id:str; records:list[ConfidenceRecord]=field(default_factory=list)
@dataclass
class KnowledgeConfidenceResult: result_id:str; assessment:ConfidenceAssessment; record_count:int=0
