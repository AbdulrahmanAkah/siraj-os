from src.application.historical_intelligence.layer_adapter import IntelligenceLayerArchitect,IntelligenceLayerRuntime
class CounterfactualConstraintArchitect(IntelligenceLayerArchitect):
 def __init__(self):super().__init__("COUNTERFACTUAL")
class CounterfactualConstraintRuntime(IntelligenceLayerRuntime):
 def __init__(self):super().__init__("COUNTERFACTUAL")
