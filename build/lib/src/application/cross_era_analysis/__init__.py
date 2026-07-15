from src.application.historical_intelligence.layer_adapter import IntelligenceLayerArchitect,IntelligenceLayerRuntime
class CrossEraAnalysisArchitect(IntelligenceLayerArchitect):
 def __init__(self):super().__init__("CROSS_ERA")
class CrossEraAnalysisRuntime(IntelligenceLayerRuntime):
 def __init__(self):super().__init__("CROSS_ERA")
from .models import *
