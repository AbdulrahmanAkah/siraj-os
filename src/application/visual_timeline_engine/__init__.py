from src.application.documentary_production import DocumentaryProductionRuntime,VisualTimeline
class VisualTimelineArchitect:
 def build_policy(self):return {"policy_id":"visual_timeline"}
class VisualTimelineRuntime:
 def build_visual_timeline(self,specification,script_sections):return DocumentaryProductionRuntime().build_all(specification,script_sections)[2]
