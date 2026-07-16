from src.application.documentary_production import DocumentaryProductionRuntime,NarrationPlan,NarrationUnit
class NarrationRuntimeArchitect:
 def build_policy(self):return {"policy_id":"narration_runtime","new_text_forbidden":True}
class NarrationRuntime:
 def build_narration_plan(self,specification,script_sections):return DocumentaryProductionRuntime().narration(specification,script_sections)
