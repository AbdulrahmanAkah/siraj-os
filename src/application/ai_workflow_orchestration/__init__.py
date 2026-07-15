from src.application.ai_integration import AIIntegrationGateway
class AIWorkflowArchitect:
 def build_definition(self):return ["VALIDATE_REQUEST","RESOLVE_PROMPT","BUILD_CONTEXT","EXECUTE_PROVIDER","ENFORCE_CITATIONS","VALIDATE_OUTPUT","AUDIT"]
class AIWorkflowRuntime:
 def execute(self,provider,prompt,evidence_ids,text):return AIIntegrationGateway().execute(provider,prompt,evidence_ids,text)
