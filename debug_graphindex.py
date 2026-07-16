from src.domain.knowledge_graph.graph_index import GraphIndex
import inspect

print("FILE:")
print(inspect.getfile(GraphIndex))

print()

print("METHODS:")

for m in dir(GraphIndex):
    if not m.startswith("_"):
        print(m)