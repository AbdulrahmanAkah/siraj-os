from .runtime import HistoricalIntelligenceArchitect, HistoricalIntelligenceRuntime


class IntelligenceLayerArchitect:
    """Narrow, deterministic policy boundary for one registered intelligence layer."""

    def __init__(self, layer):
        self.layer = layer
        self._delegate = HistoricalIntelligenceArchitect()

    def build_plan(self):
        return self._delegate.build_plan(self.layer)


class IntelligenceLayerRuntime:
    """Side-effect-free adapter that exposes one registered intelligence layer."""

    def __init__(self, layer):
        self.layer = layer
        self._delegate = HistoricalIntelligenceRuntime()

    def analyze(self, subjects, evidence_ids=(), event_ids=(), claim_ids=(), reasoning_ids=()):
        plan = IntelligenceLayerArchitect(self.layer).build_plan()
        return self._delegate.analyze(plan, subjects, evidence_ids, event_ids, claim_ids, reasoning_ids)

    def validate(self, result):
        return (
            result.layer == self.layer
            and result.validation_state == "VALID"
            and result.findings == sorted(result.findings, key=lambda item: item.position)
            and all(item.trace and item.coverage for item in result.findings)
        )
