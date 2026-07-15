from src.application.operations_common import deterministic_id,integrity_hash,stable_unique
from .models import *
class AIProviderError(Exception):pass
class DeterministicTestProvider:
 def __init__(self,responses=None,fail=False):self.responses=responses or {};self.fail=fail
 def generate(self,request):
  if self.fail:raise AIProviderError("PROVIDER_FAILURE")
  key=request.get("prompt_id","");return {"request_id":deterministic_id("ai_request",request),"text":self.responses.get(key,request.get("text","")),"citations":request.get("evidence_ids",[])}
 def describe_capabilities(self):return ["TEXT_GENERATION","STRUCTURED_OUTPUT","CITATION_AWARE_OUTPUT","DETERMINISTIC_SEED"]
class NullAIProvider:
 def generate(self,request):raise AIProviderError("NULL_PROVIDER")
class AIIntegrationGateway:
 def execute(self,provider,prompt,evidence_ids,request_text):
  if not prompt.version or not prompt.template:raise ValueError("Invalid prompt contract")
  evidence=stable_unique(evidence_ids);context=EvidenceContext(deterministic_id("evidence_context",evidence),evidence,[],integrity_hash(evidence));response=provider.generate({"prompt_id":prompt.prompt_id,"text":request_text,"evidence_ids":evidence});citations=stable_unique(response.get("citations",[]));trace=AITrace(deterministic_id("ai_trace",[evidence,citations]),evidence_ids=evidence,citation_ids=citations);generation=GroundedGenerationResult(deterministic_id("grounded_generation",[response["text"],citations]),response["text"],citations,[],trace)
  issues=[]
  if prompt.citation_policy=="REQUIRED" and not citations:issues.append(AIValidationIssue(deterministic_id("ai_issue","MISSING_CITATION"),"MISSING_CITATION",generation.result_id,"ERROR"))
  if any(x not in evidence for x in citations):issues.append(AIValidationIssue(deterministic_id("ai_issue",citations),"FABRICATED_REFERENCE",generation.result_id,"CRITICAL"))
  status="REJECTED" if any(x.severity=="CRITICAL" for x in issues) else ("REQUIRES_REVIEW" if issues else "VALID");validation=AIOutputValidationReport(deterministic_id("ai_validation",[status,[x.issue_id for x in issues]]),status,issues);identity=PromptIdentity(prompt.prompt_id,prompt.version,integrity_hash(prompt.template));audit=AIAuditRecord(deterministic_id("ai_audit",[response["request_id"],identity.prompt_hash,context.context_hash]),response["request_id"],identity,ContextIdentity(context.context_id,context.context_hash),integrity_hash(response["text"]),integrity_hash(validation),0);return ValidatedGroundedAIResult(deterministic_id("validated_ai",[generation.result_id,validation.report_id]),generation,validation,audit,status)
