from dataclasses import dataclass


@dataclass
class RankedSource:

    title:str

    score:float

    reason:str


class SourceRankingEngine:

    def rank(

        self,

        graph,

    ):

        node_types=getattr(

            graph.index,

            "nodes_by_type",

            {}

        )

        claims=len(node_types.get("CLAIM",[]))

        persons=len(node_types.get("PERSON",[]))

        events=len(node_types.get("EVENT",[]))

        statistics=len(node_types.get("STATISTIC",[]))

        sources=node_types.get("SOURCE",[])

        ranked=[]

        for node in sources:

            d=node.data

            title=d["title"] if isinstance(d,dict) else getattr(d,"title","")

            score=claims*1.0+persons*2.0+events*2.0+statistics*1.5

            ranked.append(

                RankedSource(

                    title=title,

                    score=round(score,2),

                    reason="knowledge coverage",

                )

            )

        ranked.sort(

            key=lambda x:x.score,

            reverse=True,

        )

        return ranked


__all__=["RankedSource","SourceRankingEngine"]


