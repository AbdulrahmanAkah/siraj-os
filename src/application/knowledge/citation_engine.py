from dataclasses import dataclass


@dataclass
class Citation:

    claim:str

    source_title:str

    confidence:float



class CitationEngine:

    def build(

        self,

        graph,

    ):

        node_types=getattr(

            graph.index,

            "nodes_by_type",

            {}

        )

        sources=node_types.get("SOURCE",[])

        source_title=""

        if sources:

            s=sources[0].data

            source_title=s["title"] if isinstance(s,dict) else getattr(s,"title","")

        citations=[]

        for claim in node_types.get("CLAIM",[]):

            d=claim.data

            text=d["text"] if isinstance(d,dict) else getattr(d,"text","")

            citations.append(

                Citation(

                    claim=text,

                    source_title=source_title,

                    confidence=1.0,

                )

            )

        return citations


__all__=["Citation","CitationEngine"]


