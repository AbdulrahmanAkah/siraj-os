from src.core.knowledge_asset import KnowledgeAsset
from src.domain.knowledge_objects.entity import Person
from src.domain.knowledge_objects.source import Source

valid_asset = KnowledgeAsset(title="Battle of Badr")
valid_asset.add_source(Source(title="Sahih Muslim"))
valid_asset.add_entity(Person(name="Muhammad", arabic_name="Ù…Ø­Ù…Ø¯ ï·º"))

invalid_asset = KnowledgeAsset(title="")

print(valid_asset.validate())
print(invalid_asset.validate())


