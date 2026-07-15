from dataclasses import dataclass,field,asdict
from src.application.operations_common import deterministic_id,integrity_hash
from .credentials import EnvironmentCredentialResolver
@dataclass
class SecretReference: reference:str
@dataclass
class SecurityConfig: data_classification:str="INTERNAL"; secret_reference:SecretReference|None=None
@dataclass
class RuntimeConfig: mode:str="LOCAL"; json_output:bool=False
@dataclass
class SQLiteConfig: path:str=""; read_only:bool=False; timeout:float=5.0
@dataclass
class PersistenceConfig: backend:str="MEMORY"; sqlite:SQLiteConfig=field(default_factory=SQLiteConfig)
@dataclass
class ExportConfig: output_root:str=""; overwrite_policy:str="DENY"; maximum_file_size:int=5_000_000
@dataclass
class RendererConfig: mode:str="DRY_RUN"; allowed_asset_root:str=""
@dataclass
class ApplicationConfig:
 schema_version:str="v1"; runtime:RuntimeConfig=field(default_factory=RuntimeConfig); security:SecurityConfig=field(default_factory=SecurityConfig); persistence:PersistenceConfig=field(default_factory=PersistenceConfig); export:ExportConfig=field(default_factory=ExportConfig); renderer:RendererConfig=field(default_factory=RendererConfig); unknown_key_policy:str="REJECT"
 def fingerprint(self):return integrity_hash(self.redacted())
 def redacted(self):return {"schema_version":self.schema_version,"runtime":asdict(self.runtime),"security":{"data_classification":self.security.data_classification,"secret_reference":"REDACTED" if self.security.secret_reference else None},"persistence":asdict(self.persistence),"export":asdict(self.export),"renderer":asdict(self.renderer)}
class ConfigurationLoader:
 def load(self,defaults=None,file_values=None,environment=None,overrides=None):
  values={};
  for source in (defaults or {},file_values or {},environment or {},overrides or {}):values.update(source)
  allowed={"mode","json_output","data_classification","secret_reference","persistence.backend","persistence.sqlite.path","persistence.sqlite.read_only","persistence.sqlite.timeout","export.output_root","export.overwrite_policy","export.maximum_file_size","renderer.mode","renderer.allowed_asset_root"};unknown=set(values)-allowed
  if unknown:raise ValueError("UNKNOWN_CONFIGURATION_KEY")
  return ApplicationConfig(runtime=RuntimeConfig(values.get("mode","LOCAL"),bool(values.get("json_output",False))),security=SecurityConfig(values.get("data_classification","INTERNAL"),SecretReference(values["secret_reference"]) if values.get("secret_reference") else None),persistence=PersistenceConfig(values.get("persistence.backend","MEMORY"),SQLiteConfig(values.get("persistence.sqlite.path",""),bool(values.get("persistence.sqlite.read_only",False)),float(values.get("persistence.sqlite.timeout",5.0)))),export=ExportConfig(values.get("export.output_root",""),values.get("export.overwrite_policy","DENY"),int(values.get("export.maximum_file_size",5_000_000))),renderer=RendererConfig(values.get("renderer.mode","DRY_RUN"),values.get("renderer.allowed_asset_root","")))
