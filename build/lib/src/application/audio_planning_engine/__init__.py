from src.application.documentary_production import DocumentaryProductionRuntime,AudioPlan
class AudioPlanningArchitect:
 def build_policy(self):return {"policy_id":"audio_planning","rights_default":"RIGHTS_UNVERIFIED"}
class AudioPlanningRuntime:
 def build_audio_plan(self,specification,script_sections):return DocumentaryProductionRuntime().build_all(specification,script_sections)[5]
