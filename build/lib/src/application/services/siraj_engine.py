from src.application.knowledge_v2.pipeline import KnowledgeExtractionPipeline
from src.application.models.outline import Outline
from src.core.knowledge_asset import KnowledgeAsset


class SirajEngine:
    def build_outline(self, asset: KnowledgeAsset) -> Outline:
        entities = []
        claims = []
        sources = []

        for entity in asset.entities:
            if entity.name:
                entities.append(entity.name)

        for claim in asset.claims:
            if claim.text:
                claims.append(claim.text)

        for source in asset.sources:
            if source.title:
                sources.append(source.title)

        return Outline(
            title=asset.title,
            description=asset.description,
            entities=entities,
            claims=claims,
            sources=sources,
        )


__all__ = ["SirajEngine"]


