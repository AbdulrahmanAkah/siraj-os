from dataclasses import dataclass


@dataclass
class Narrative:
    introduction: str
    body: list[str]
    conclusion: str


def _field(data, key, default=""):
    if isinstance(data, dict):
        return data.get(key, default)
    return getattr(data, key, default)


class NarrativeBuilder:

    def build(self, graph, outline) -> Narrative:
        node_types = getattr(graph.index, "nodes_by_type", {})
        body = []

        for index, section in enumerate(outline.sections):
            if index == 0:
                names = [
                    _field(node.data, "name")
                    for node in node_types.get("PERSON", [])
                ]
                names += [
                    _field(node.data, "name")
                    for node in node_types.get("ORGANIZATION", [])
                ]
                names = [name for name in names if name]
                paragraph = (
                    f"The section introduces {', '.join(names)} as documented figures or groups connected to the subject."
                    if names else
                    "The source contains no named figures or groups for this section."
                )
            elif index == 1:
                values = [
                    _field(node.data, "name", _field(node.data, "title"))
                    for node in node_types.get("EVENT", [])
                ]
                values = [value for value in values if value]
                paragraph = (
                    f"The documented events include {', '.join(values)}."
                    if values else
                    "No event details were extracted for this section."
                )
            elif index == 2:
                values = [
                    f"{_field(node.data, 'date')}: {_field(node.data, 'title')}"
                    for node in node_types.get("TIMELINE_EVENT", [])
                ]
                paragraph = (
                    "The available chronology records " + "; ".join(values) + "."
                    if values else
                    "No dated events were extracted for this section."
                )
            elif index == 3:
                values = [
                    _field(node.data, "name")
                    for node in node_types.get("LOCATION", [])
                ]
                values = [value for value in values if value]
                paragraph = (
                    f"The documented locations include {', '.join(values)}."
                    if values else
                    "No location details were extracted for this section."
                )
            else:
                claims = [
                    _field(node.data, "text")
                    for node in node_types.get("CLAIM", [])
                ]
                claims = [claim for claim in claims if claim]
                relationships = []
                for edge in getattr(graph, "relationships", []):
                    relationships.append(
                        f"{edge.source} {edge.relation} {edge.target}"
                    )
                details = claims + relationships
                paragraph = (
                    "The extracted record states that " + "; ".join(details) + "."
                    if details else
                    "No factual statements or relationships were extracted for this section."
                )

            body.append(paragraph)

        return Narrative(
            introduction=outline.introduction or f"This documentary examines {outline.title}.",
            body=body,
            conclusion=outline.conclusion or f"The documentary concludes with the evidence recorded for {outline.title}.",
        )


__all__ = ["Narrative", "NarrativeBuilder"]
