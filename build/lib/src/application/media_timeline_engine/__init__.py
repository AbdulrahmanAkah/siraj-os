from src.application.documentary_production import DocumentaryProductionRuntime,MediaTimeline
class MediaTimelineArchitect:
 def build_policy(self):return {"policy_id":"media_timeline"}
class MediaTimelineRuntime:
 def build_media_timeline(self,specification,script_sections):return DocumentaryProductionRuntime().build_all(specification,script_sections)[3]
