from src.application.historical_intelligence import HistoricalIntelligenceArchitect,HistoricalIntelligenceRuntime,LAYERS
def test_bundle_g_deterministic_integrated_intelligence_chain():
 architect=HistoricalIntelligenceArchitect();runtime=HistoricalIntelligenceRuntime()
 first=[runtime.analyze(architect.build_plan(layer),["event-b","event-a"],["evidence-a"],["event-a","event-b"],["claim-a"],["reasoning-a"]) for layer in LAYERS]
 second=[runtime.analyze(architect.build_plan(layer),["event-a","event-b"],["evidence-a"],["event-b","event-a"],["claim-a"],["reasoning-a"]) for layer in reversed(LAYERS)]
 package=runtime.synthesize(first);again=runtime.synthesize(second);validated=runtime.validate(package)
 assert package==again
 assert validated.status=="VALID"
 assert all(f.trace.evidence_ids==["evidence-a"] for r in package.results for f in r.findings)
