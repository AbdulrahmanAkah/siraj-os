from src.application.comparative_historical_analysis import ComparativeHistoricalAnalysisArchitect,ComparativeHistoricalAnalysisRuntime
from src.application.cross_era_analysis import CrossEraAnalysisArchitect,CrossEraAnalysisRuntime
from src.application.historical_pattern_detection import HistoricalPatternDetectionArchitect,HistoricalPatternDetectionRuntime
from src.application.civilization_analysis import CivilizationAnalysisArchitect,CivilizationAnalysisRuntime
from src.application.institutional_evolution import InstitutionalEvolutionArchitect,InstitutionalEvolutionRuntime
from src.application.strategic_historical_analysis import StrategicHistoricalAnalysisArchitect,StrategicHistoricalAnalysisRuntime
from src.application.long_horizon_trends import LongHorizonTrendArchitect,LongHorizonTrendRuntime
from src.application.counterfactual_constraints import CounterfactualConstraintArchitect,CounterfactualConstraintRuntime
from src.application.historical_theory import HistoricalTheoryArchitect,HistoricalTheoryRuntime
from src.application.intelligence_synthesis import IntelligenceSynthesisRuntime
from src.application.intelligence_validation import IntelligenceValidationRuntime

def test_all_bundle_g_public_layers_are_deterministic_and_traceable():
    pairs=[(ComparativeHistoricalAnalysisArchitect,ComparativeHistoricalAnalysisRuntime),(CrossEraAnalysisArchitect,CrossEraAnalysisRuntime),(HistoricalPatternDetectionArchitect,HistoricalPatternDetectionRuntime),(CivilizationAnalysisArchitect,CivilizationAnalysisRuntime),(InstitutionalEvolutionArchitect,InstitutionalEvolutionRuntime),(StrategicHistoricalAnalysisArchitect,StrategicHistoricalAnalysisRuntime),(LongHorizonTrendArchitect,LongHorizonTrendRuntime),(CounterfactualConstraintArchitect,CounterfactualConstraintRuntime),(HistoricalTheoryArchitect,HistoricalTheoryRuntime)]
    results=[]
    for architect_type,runtime_type in pairs:
        runtime=runtime_type(); plan=architect_type().build_plan(); result=runtime.analyze(["entity-b","entity-a"],["evidence-1"],["event-2","event-1"],["claim-1"],["reasoning-1"])
        assert result.layer==plan["layer"] and runtime.validate(result)
        assert result.findings[0].subject_ids==["entity-a","entity-b"]
        results.append(result)
    package=IntelligenceSynthesisRuntime().synthesize(results)
    validated=IntelligenceValidationRuntime().validate(package)
    assert validated.status=="VALID"
