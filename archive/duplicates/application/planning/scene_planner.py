from application.planning.scene_plan import ScenePlan


class ScenePlanner:

    def plan(
        self,
        graph,
        outline,
    ):

        node_types = getattr(
            graph.index,
            "nodes_by_type",
            {}
        )

        plans = []

        mapping = {
            "PERSON": "PERSON",
            "EVENT": "EVENT",
            "TIMELINE_EVENT": "TIMELINE_EVENT",
            "LOCATION": "LOCATION",
            "STATISTIC": "STATISTIC",
            "CLAIM": "CLAIM",
        }

        for index, section in enumerate(outline.sections, start=1):

            key_points = []

            node_type = mapping.get(section)

            if node_type:
                for node in node_types.get(node_type, []):
                    data = node.data

                    text = (
                        data.get("name")
                        or data.get("title")
                        or data.get("text")
                        or data.get("value")
                    )

                    if text:
                        key_points.append(text)

            plans.append(
                ScenePlan(
                    index=index,
                    title=section,
                    objective=f"Explain {section}",
                    key_points=key_points,
                )
            )

        return plans


__all__ = ["ScenePlanner"]
