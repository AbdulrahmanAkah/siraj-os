from src.application.models.outline import DocumentaryOutline


class KnowledgeOutlineBuilder:

    def build(
        self,
        graph,
        topic: str,
    ) -> DocumentaryOutline:


        node_types = getattr(
            graph.index,
            "nodes_by_type",
            {}
        )


        sections = []


        mapping = [
            ("PERSON", "الشخصيات"),
            ("EVENT", "الأحداث"),
            ("TIMELINE_EVENT", "التسلسل الزمني"),
            ("LOCATION", "الأماكن"),
            ("STATISTIC", "الإحصاءات"),
            ("CLAIM", "الحقائق والعلاقات"),
        ]


        for node_type, title in mapping:

            if node_types.get(node_type):

                sections.append(title)



        return DocumentaryOutline(
            title=topic,
            introduction=f"يستعرض هذا الفيلم الوثائقي موضوع {topic} اعتماداً على المعرفة المستخرجة من المصادر.",
            sections=sections,
            conclusion="تقدم الحلقة صورة مترابطة مبنية على الأحداث والشخصيات والحقائق المستخرجة.",
        )


__all__ = [
    "KnowledgeOutlineBuilder"
]
