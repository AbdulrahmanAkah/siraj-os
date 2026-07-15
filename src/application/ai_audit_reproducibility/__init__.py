from src.application.operations_common import integrity_hash
class AIAuditReproducibilityRuntime:
 def manifest(self,result):return {"audit_id":result.audit.audit_id,"request_hash":integrity_hash(result.audit.provider_request_id),"response_hash":result.audit.raw_output_hash,"validation_hash":result.audit.validation_hash}
