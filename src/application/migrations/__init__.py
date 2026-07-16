from dataclasses import dataclass
@dataclass
class MigrationResult: source_version:str; target_version:str; applied:bool; dry_run:bool
class MigrationRuntime:
 def migrate(self,value,source_version,target_version,dry_run=True):
  if source_version==target_version:return MigrationResult(source_version,target_version,False,dry_run)
  if dry_run:return MigrationResult(source_version,target_version,False,True)
  return MigrationResult(source_version,target_version,True,False)
