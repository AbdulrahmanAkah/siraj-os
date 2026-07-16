from src.application.historical_intelligence.layer_adapter import IntelligenceLayerArchitect,IntelligenceLayerRuntime
class LongHorizonTrendArchitect(IntelligenceLayerArchitect):
 def __init__(self):super().__init__("TREND")
class LongHorizonTrendRuntime(IntelligenceLayerRuntime):
 def __init__(self):super().__init__("TREND")
