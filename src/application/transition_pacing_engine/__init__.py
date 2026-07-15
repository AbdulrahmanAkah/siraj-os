from src.application.documentary_production import DocumentaryProductionRuntime,PacingPlan,TransitionPlan
class TransitionPacingArchitect:
 def build_policy(self):return {"policy_id":"transition_pacing","types":["CUT","FADE","DISSOLVE","HOLD","TEXT_CARD","MAP_TRANSITION","DOCUMENT_TRANSITION","NONE"]}
class TransitionPacingRuntime:
 def build_plans(self,specification,script_sections):
  output=DocumentaryProductionRuntime().build_all(specification,script_sections);return output[7],output[8]
