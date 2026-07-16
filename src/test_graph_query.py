from src.application.knowledge.extraction_pipeline import ExtractionPipeline
from src.application.knowledge.graph_query import GraphQuery


text = """

Battle of Badr happened in 624 CE.

Muhammad commanded Muslim Army.

Muslims defeated Quraysh.

Badr is southwest of Madinah.

"""


pipeline = ExtractionPipeline()

graph = pipeline.run(text)

query = GraphQuery(graph)


print("PERSONS")

for p in query.nodes_of_type("PERSON"):

    print(p)


print()

print("OUTGOING MUHAMMAD")

for e in query.outgoing("muhammad"):

    print(e)


