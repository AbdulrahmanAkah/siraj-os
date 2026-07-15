from src.application.documentary_production import DocumentaryProductionRuntime,DocumentaryProductionSpecification
class ProductionSpecificationArchitect:
 def build_profile(self):return {"frame_rate_num":25,"time_unit":"MILLISECONDS"}
class ProductionSpecificationRuntime:
 def build_specification(self,production_id,scene_ids,language="ar",duration_target_ms=None):return DocumentaryProductionRuntime().specification(production_id,scene_ids,language,duration_target_ms)
