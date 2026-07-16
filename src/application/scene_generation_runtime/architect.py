from src.application.documentary_intelligence import CANONICAL_CREATED_AT,canonical_trace,deterministic_id
from .models import SceneGenerationPolicy
class SceneGenerationArchitect:
 def build_scene_generation_policy(self): return SceneGenerationPolicy(deterministic_id("scene_generation_policy",["ONE_SCENE_PER_SECTION"]),CANONICAL_CREATED_AT,0,canonical_trace())
 def validate_policy(self,p): return isinstance(p,SceneGenerationPolicy) and p.created_at==CANONICAL_CREATED_AT
