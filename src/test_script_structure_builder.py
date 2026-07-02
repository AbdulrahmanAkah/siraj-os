from application.services.script_structure_builder import ScriptStructureBuilder
from application.services.siraj_engine import SirajEngine
from core.knowledge_asset import KnowledgeAsset
from domain.claims.claim import Claim
from domain.entities.entity import Person
from domain.sources.source import Source

asset = KnowledgeAsset(title="Battle of Badr", description="First major battle")
asset.add_entity(Person(name="Muhammad", arabic_name="محمد ﷺ"))
asset.add_source(Source(title="Sahih Muslim"))
asset.add_claim(Claim(text="The Battle of Badr occurred in the second year after Hijrah."))

outline = SirajEngine().build_outline(asset)
script_structure = ScriptStructureBuilder().build(outline)
print(script_structure)
