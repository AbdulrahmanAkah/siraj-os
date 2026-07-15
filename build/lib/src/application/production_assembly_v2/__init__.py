from src.application.documentary_production import DocumentaryProductionRuntime,DocumentaryProductionPackage
class ProductionAssemblyArchitectV2:
 def build_policy(self):return {"policy_id":"production_assembly_v2","references_only":True}
class ProductionAssemblyRuntimeV2:
 def build_package(self,specification,script_sections):return DocumentaryProductionRuntime().build_all(specification,script_sections)[10]
