from src.application.historical_intelligence.layer_adapter import IntelligenceLayerArchitect,IntelligenceLayerRuntime
class CivilizationAnalysisArchitect(IntelligenceLayerArchitect):
 def __init__(self):super().__init__("CIVILIZATION")
class CivilizationAnalysisRuntime(IntelligenceLayerRuntime):
 def __init__(self):super().__init__("CIVILIZATION")
from .models import *
