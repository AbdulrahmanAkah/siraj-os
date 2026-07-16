from src.application.historical_intelligence.layer_adapter import IntelligenceLayerArchitect,IntelligenceLayerRuntime
class HistoricalPatternDetectionArchitect(IntelligenceLayerArchitect):
 def __init__(self):super().__init__("PATTERN")
class HistoricalPatternDetectionRuntime(IntelligenceLayerRuntime):
 def __init__(self):super().__init__("PATTERN")
from .models import *
