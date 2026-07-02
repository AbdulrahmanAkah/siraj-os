from core.knowledge_asset import KnowledgeAsset
from domain.entities.entity import Person
from domain.sources.source import Source

valid_asset = KnowledgeAsset(title="Battle of Badr")
valid_asset.add_source(Source(title="Sahih Muslim"))
valid_asset.add_entity(Person(name="Muhammad", arabic_name="محمد ﷺ"))

invalid_asset = KnowledgeAsset(title="")

print(valid_asset.validate())
print(invalid_asset.validate())
