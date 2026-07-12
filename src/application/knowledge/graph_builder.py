from .canonicalizer import Canonicalizer

from src.domain.knowledge_graph.knowledge_graph import KnowledgeGraph
from src.domain.knowledge_graph.knowledge_node import KnowledgeNode
from src.domain.knowledge_graph.knowledge_edge import KnowledgeEdge


class GraphBuilder:


    def build(self, extractions):

        if not isinstance(extractions, list):
            extractions = [extractions]


        graph = KnowledgeGraph()


        def add(obj, node_type, node_id):

            graph.add_node(
                KnowledgeNode(
                    id=node_id,
                    type=node_type,
                    data=obj.to_dict(),
                )
            )


        for extraction in extractions:


            for x in extraction.persons:

                add(
                    x,
                    "PERSON",
                    Canonicalizer.canonical_name(x.name),
                )


            for x in extraction.events:

                add(
                    x,
                    "EVENT",
                    Canonicalizer.normalize_text(x.name),
                )


            for x in extraction.locations:

                add(
                    x,
                    "LOCATION",
                    Canonicalizer.canonical_name(x.name),
                )


            for i,x in enumerate(extraction.claims):

                add(
                    x,
                    "CLAIM",
                    f"claim_{i}",
                )


            for i,x in enumerate(extraction.statistics):

                add(
                    x,
                    "STATISTIC",
                    f"statistic_{i}",
                )


            for i,x in enumerate(extraction.timeline):

                add(
                    x,
                    "TIMELINE_EVENT",
                    f"timeline_{i}",
                )


            for i,x in enumerate(extraction.sources):

                add(
                    x,
                    "SOURCE",
                    f"source_{i}",
                )


            for r in extraction.relationships:

                source = Canonicalizer.normalize_text(
                    r.subject
                )

                target = Canonicalizer.normalize_text(
                    r.object
                )


                if graph.get_node(source) is None:

                    graph.add_node(
                        KnowledgeNode(
                            id=source,
                            type="ENTITY",
                            data={
                                "name": r.subject
                            },
                        )
                    )


                if graph.get_node(target) is None:

                    graph.add_node(
                        KnowledgeNode(
                            id=target,
                            type="ENTITY",
                            data={
                                "name": r.object
                            },
                        )
                    )


                graph.add_edge(
                    KnowledgeEdge(
                        source=source,
                        target=target,
                        relation=Canonicalizer.normalize_text(
                            r.predicate
                        ),
                    )
                )


        graph.refresh()

        return graph



__all__ = [
    "GraphBuilder"
]
