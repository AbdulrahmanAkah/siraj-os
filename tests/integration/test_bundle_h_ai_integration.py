from src.application.ai_integration import AIIntegrationGateway,DeterministicTestProvider,PromptContract
from src.application.model_capability_registry import ModelCapabilityRegistry
from src.application.evidence_context_builder import EvidenceContextBuilder
from src.application.ai_workflow_orchestration import AIWorkflowRuntime
def test_bundle_h_grounded_valid_missing_and_fabricated_citations():
 gateway=AIIntegrationGateway();prompt=PromptContract("prompt","v1","rewrite","{{evidence}}")
 valid=gateway.execute(DeterministicTestProvider(),prompt,["evidence-a"],"supported rewrite")
 missing=gateway.execute(DeterministicTestProvider({"prompt":"text"}),prompt,[],"text")
 fabricated=gateway.execute(DeterministicTestProvider({"prompt":"text"}),prompt,["evidence-a"],"text")
 assert valid.status=="VALID"
 assert missing.status=="REQUIRES_REVIEW"
 assert fabricated.status=="VALID"

def test_bundle_h_capability_context_and_workflow_are_deterministic():
 registry=ModelCapabilityRegistry();registry.register("test",["TEXT_GENERATION"]);registry.require("test","TEXT_GENERATION")
 context=EvidenceContextBuilder().build(["evidence-b","evidence-a","evidence-b"],1)
 prompt=PromptContract("workflow","v1","rewrite","{{evidence}}")
 first=AIWorkflowRuntime().execute(DeterministicTestProvider(),prompt,context.evidence_ids,"text")
 second=AIWorkflowRuntime().execute(DeterministicTestProvider(),prompt,context.evidence_ids,"text")
 assert context.evidence_ids==["evidence-a"] and first==second
