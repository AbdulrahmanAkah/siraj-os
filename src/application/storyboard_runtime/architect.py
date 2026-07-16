from src.application.documentary_intelligence import CANONICAL_CREATED_AT,canonical_trace,deterministic_id
from .models import StoryboardPolicy
class StoryboardArchitectRuntime:
 def build_storyboard_policy(self): return StoryboardPolicy(deterministic_id("storyboard_policy",["ONE_FRAME_PER_SCENE"]),CANONICAL_CREATED_AT,0,canonical_trace())
 def validate_policy(self,p): return isinstance(p,StoryboardPolicy) and p.created_at==CANONICAL_CREATED_AT
