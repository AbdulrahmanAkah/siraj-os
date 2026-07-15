from src.application.documentary_production import DocumentaryProductionRuntime,SubtitlePackage
class SubtitleCaptionArchitect:
 def build_policy(self):return {"policy_id":"subtitle_caption","translation":"EXPLICIT_ONLY"}
class SubtitleCaptionRuntime:
 def build_subtitle_package(self,specification,script_sections):return DocumentaryProductionRuntime().build_all(specification,script_sections)[4]
