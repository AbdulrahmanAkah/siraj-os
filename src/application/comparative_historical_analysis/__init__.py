from src.application.historical_intelligence.layer_adapter import IntelligenceLayerArchitect,IntelligenceLayerRuntime
class ComparativeHistoricalAnalysisArchitect(IntelligenceLayerArchitect):
 def __init__(self):super().__init__("COMPARATIVE")
class ComparativeHistoricalAnalysisRuntime(IntelligenceLayerRuntime):
 def __init__(self):super().__init__("COMPARATIVE")
from .models import *
