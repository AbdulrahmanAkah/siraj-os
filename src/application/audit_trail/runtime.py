from src.application.operations_common import *
from .models import AuditEvent,AuditTrail
class AuditTrailRuntime:
 def build_audit_trail(self,policy,actions):
  events=[AuditEvent(deterministic_id("audit_event",[a["actor"],a["action"],a["reason"],a["subject_id"]]),a["actor"],a["action"],a["reason"],a["subject_id"],CANONICAL_TIMESTAMP,pos,canonical_version_metadata(a["subject_id"]),{}) for pos,a in enumerate(actions)]
  return AuditTrail(deterministic_id("audit_trail",[x.event_id for x in events]),events,len(events),CANONICAL_TIMESTAMP,0,canonical_version_metadata("audit_trail"),{},"VALID")
