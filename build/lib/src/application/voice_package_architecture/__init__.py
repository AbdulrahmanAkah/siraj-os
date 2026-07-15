from src.application.documentary_production import VoicePackage
class VoicePackageArchitect:
 def build_policy(self):return {"policy_id":"voice_package","synthesis_forbidden":True}
class VoicePackageRuntime:
 def build_voice_package(self,narration_plan):return VoicePackage("voice_"+narration_plan.plan_id,[x.unit_id for x in narration_plan.units])
