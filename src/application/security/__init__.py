from dataclasses import dataclass
@dataclass
class PolicyDecision: decision:str; rule_id:str
class SecurityPolicyEngine:
 def decide(self,action,classification="INTERNAL"):
  if action in {"WRITE","EXPORT"} and classification=="RESTRICTED":return PolicyDecision("DENY","RESTRICTED_EXPORT_DENY")
  if action=="LOAD_PLUGIN" and classification in {"SENSITIVE","RESTRICTED"}:return PolicyDecision("DENY","PLUGIN_CAPABILITY_DENY")
  if action in {"USE_NETWORK","RUN_SUBPROCESS","ACCESS_SECRET","SEND_TO_EXTERNAL_PROVIDER"}:return PolicyDecision("DENY","DEFAULT_DENY_SENSITIVE")
  return PolicyDecision("ALLOW","LOCAL_DETERMINISTIC_ALLOW")
