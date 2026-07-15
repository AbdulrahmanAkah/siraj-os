from src.application.historical_intelligence.layer_adapter import IntelligenceLayerArchitect,IntelligenceLayerRuntime
class InstitutionalEvolutionArchitect(IntelligenceLayerArchitect):
 def __init__(self):super().__init__("INSTITUTION")
class InstitutionalEvolutionRuntime(IntelligenceLayerRuntime):
 def __init__(self):super().__init__("INSTITUTION")
from .models import *
