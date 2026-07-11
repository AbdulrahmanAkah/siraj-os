from pathlib import Path


path = Path(
"src/domain/knowledge_graph/knowledge_graph.py"
)


text = path.read_text(
    encoding="utf-8"
)


old = """
    def find_by_type(self,t):

        self.refresh()

        return self.index.find_by_type(t)
"""


new = """
    def find_by_type(self,t):

        self.refresh()

        return self.index.find_by_type(t)



    def get_nodes_by_type(self,node_type):

        return self.find_by_type(node_type)
"""


if "get_nodes_by_type" not in text:

    text = text.replace(
        old,
        new
    )


path.write_text(
    text,
    encoding="utf-8"
)


print(
"GRAPH API FIX COMPLETE"
)