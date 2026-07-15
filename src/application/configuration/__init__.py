from dataclasses import dataclass,field,asdict
from src.application.operations_common import deterministic_id,integrity_hash
@dataclass
class SecretReference: reference:str
@dataclass
class SecurityConfig: data_classification:str="INTERNAL"; secret_reference:SecretReference|None=None
@dataclass
class RuntimeConfig: mode:str="LOCAL"; json_output:bool=False
@dataclass
class ApplicationConfig:
 schema_version:str="v1"; runtime:RuntimeConfig=field(default_factory=RuntimeConfig); security:SecurityConfig=field(default_factory=SecurityConfig); unknown_key_policy:str="REJECT"
 def fingerprint(self):return integrity_hash({"schema_version":self.schema_version,"runtime":asdict(self.runtime),"security":{"data_classification":self.security.data_classification,"secret_reference":None if not self.security.secret_reference else "REDACTED"}})
 def redacted(self):return {"schema_version":self.schema_version,"runtime":asdict(self.runtime),"security":{"data_classification":self.security.data_classification,"secret_reference":"REDACTED" if self.security.secret_reference else None}}
class ConfigurationLoader:
 def load(self,defaults=None,file_values=None,environment=None,overrides=None):
  values={};
  for source in (defaults or {},file_values or {},environment or {},overrides or {}):values.update(source)
  allowed={"mode","json_output","data_classification","secret_reference"};unknown=set(values)-allowed
  if unknown:raise ValueError("UNKNOWN_CONFIGURATION_KEY")
  return ApplicationConfig(runtime=RuntimeConfig(values.get("mode","LOCAL"),bool(values.get("json_output",False))),security=SecurityConfig(values.get("data_classification","INTERNAL"),SecretReference(values["secret_reference"]) if values.get("secret_reference") else None))
