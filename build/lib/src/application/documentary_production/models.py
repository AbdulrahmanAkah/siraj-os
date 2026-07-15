from dataclasses import dataclass,field
from src.application.operations_common import CANONICAL_TIMESTAMP
from src.application.production_contracts.models import ProductionTrace,ProductionLimitation,TimeRange
@dataclass
class ProductionProfile: profile_id:str; resolution:str; frame_rate_num:int; aspect_ratio:str; language:str; duration_target_ms:int
@dataclass
class DocumentaryProductionSpecification: specification_id:str; production_id:str; profile:ProductionProfile; scene_durations_ms:dict[str,int]=field(default_factory=dict); subtitle_languages:list[str]=field(default_factory=list); trace:ProductionTrace=None; limitations:list[ProductionLimitation]=field(default_factory=list); timestamp:str=CANONICAL_TIMESTAMP; validation_state:str="VALID"
@dataclass
class NarrationUnit: unit_id:str; script_ref:str; scene_id:str; text:str; time_range:TimeRange; evidence_ids:list[str]=field(default_factory=list); position:int=0; trace:ProductionTrace=None
@dataclass
class NarrationPlan: plan_id:str; units:list[NarrationUnit]=field(default_factory=list); validation_state:str="VALID"
@dataclass
class VoicePackage: package_id:str; narration_unit_ids:list[str]=field(default_factory=list); pronunciation_status:str="PRONUNCIATION_UNSPECIFIED"; validation_state:str="VALID"
@dataclass
class VisualTimeline: timeline_id:str; segments:list[dict]=field(default_factory=list); validation_state:str="VALID"
@dataclass
class MediaTimeline: timeline_id:str; tracks:dict[str,list[dict]]=field(default_factory=dict); validation_state:str="VALID"
@dataclass
class SubtitlePackage: package_id:str; cues:list[dict]=field(default_factory=list); validation_state:str="VALID"
@dataclass
class AudioPlan: plan_id:str; tracks:list[dict]=field(default_factory=list); validation_state:str="VALID"
@dataclass
class VisualPlacementResult: result_id:str; placements:list[dict]=field(default_factory=list); limitations:list[ProductionLimitation]=field(default_factory=list); validation_state:str="VALID"
@dataclass
class PacingPlan: plan_id:str; records:list[dict]=field(default_factory=list); validation_state:str="VALID"
@dataclass
class TransitionPlan: plan_id:str; transitions:list[dict]=field(default_factory=list); validation_state:str="VALID"
@dataclass
class RenderManifest: manifest_id:str; dependencies:list[str]=field(default_factory=list); missing_assets:list[str]=field(default_factory=list); validation_state:str="VALID"
@dataclass
class DocumentaryProductionPackage: package_id:str; references:dict[str,str]=field(default_factory=dict); limitations:list[ProductionLimitation]=field(default_factory=list); validation_state:str="VALID"
@dataclass
class ProductionVerificationReport: report_id:str; status:str; issues:list[dict]=field(default_factory=list)
@dataclass
class VerifiedDocumentaryProductionPackage: package_id:str; production_package_id:str; report_id:str; status:str
