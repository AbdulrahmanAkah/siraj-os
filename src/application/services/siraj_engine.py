from typing import Dict, List

from core.knowledge_asset import KnowledgeAsset


class SirajEngine:
    def build_outline(self, asset: KnowledgeAsset) -> Dict[str, object]:
        entities: List[str] = []
        claims: List[str] = []
        sources: List[str] = []

        for entity in asset.entities:
            if entity.name:
                entities.append(entity.name)

        for claim in asset.claims:
            if claim.text:
                claims.append(claim.text)

        for source in asset.sources:
            if source.title:
                sources.append(source.title)

        return {
            "title": asset.title,
            "description": asset.description,
            "entities": entities,
            "claims": claims,
            "sources": sources,
        }


__all__ = ["SirajEngine"]
