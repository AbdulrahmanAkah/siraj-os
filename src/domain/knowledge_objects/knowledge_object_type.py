from enum import Enum


class KnowledgeObjectType(str, Enum):
    PERSON = "PERSON"
    EVENT = "EVENT"
    RELATIONSHIP = "RELATIONSHIP"
    STATISTIC = "STATISTIC"
    TIMELINE_EVENT = "TIMELINE_EVENT"


__all__ = ["KnowledgeObjectType"]

