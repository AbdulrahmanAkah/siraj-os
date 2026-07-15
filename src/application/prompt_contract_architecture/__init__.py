from src.application.ai_integration import PromptContract
class PromptContractArchitect:
 def validate(self,prompt):return bool(prompt.prompt_id and prompt.version and prompt.template and prompt.output_schema)
