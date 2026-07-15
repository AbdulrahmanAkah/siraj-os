from src.application.ai_integration import AIIntegrationGateway
class GroundedGenerationRuntime:
 def generate(self,provider,prompt,context,text):return AIIntegrationGateway().execute(provider,prompt,context.evidence_ids,text).generation
