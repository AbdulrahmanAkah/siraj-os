from src.application.ai_integration import AIIntegrationGateway
class AIOutputValidationRuntime:
 def validate(self,provider,prompt,evidence_ids,text):return AIIntegrationGateway().execute(provider,prompt,evidence_ids,text).validation
