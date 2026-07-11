from pathlib import Path

path = Path("src/domain/knowledge_graph/graph_index.py")

text = path.read_text(encoding="utf-8")

def append_if_missing(name, code):
    global text
    if f"def {name}(" not in text:
        text += "\n\n" + code + "\n"

append_if_missing(
    "get_nodes_by_type",
"""
    def get_nodes_by_type(self, node_type):
        return self.find_by_type(node_type)
"""
)

append_if_missing(
    "get_outgoing",
"""
    def get_outgoing(self, node_id):
        return self.outgoing.get(node_id, [])
"""
)

append_if_missing(
    "get_incoming",
"""
    def get_incoming(self, node_id):
        return self.incoming.get(node_id, [])
"""
)

path.write_text(text, encoding="utf-8")

print("GraphIndex repaired.")