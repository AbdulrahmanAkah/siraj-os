from dataclasses import dataclass, field


@dataclass
class ScenePlan:
    index: int
    title: str
    objective: str
    key_points: list[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "index": self.index,
            "title": self.title,
            "objective": self.objective,
            "key_points": self.key_points,
        }


class ScenePlanner:

    def plan(self, graph, outline):
        node_types = getattr(graph.index, "nodes_by_type", {})
        section_types = ["PERSON", "EVENT", "TIMELINE_EVENT", "LOCATION", "STATISTIC", "CLAIM"]
        plans = []

        for index, title in enumerate(outline.sections):
            node_type = section_types[index] if index < len(section_types) else "CLAIM"
            key_points = []

            for node in node_types.get(node_type, []):
                data = node.data
                value = data.get("text", data.get("title", data.get("name", data.get("value", ""))))
                if value:
                    key_points.append(f"Documented detail: {value}")

            if not key_points:
                key_points.append(f"No extracted detail is available for {title}.")

            plans.append(ScenePlan(
                index=index,
                title=title,
                objective=f"Present the documented evidence for {title} using the listed details.",
                key_points=key_points,
            ))

        return plans


__all__ = ["ScenePlan", "ScenePlanner"]
