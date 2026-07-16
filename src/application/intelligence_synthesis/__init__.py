from src.application.historical_intelligence.runtime import HistoricalIntelligenceRuntime
class IntelligenceSynthesisArchitect:
 def build_plan(self):return {"plan_id":"intelligence_synthesis"}
class IntelligenceSynthesisRuntime:
 def synthesize(self,results):return HistoricalIntelligenceRuntime().synthesize(results)
