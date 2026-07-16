from src.application.historical_intelligence.runtime import HistoricalIntelligenceRuntime
class IntelligenceValidationArchitect:
 def build_plan(self):return {"plan_id":"intelligence_validation"}
class IntelligenceValidationRuntime:
 def validate(self,package):return HistoricalIntelligenceRuntime().validate(package)
