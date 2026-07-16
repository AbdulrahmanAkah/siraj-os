from src.domain.knowledge_objects.statistic import Statistic

stat = Statistic()

assert stat.value == ""
assert stat.unit == ""
assert stat.metadata == {}

print(stat.to_dict())

stat = Statistic(
    value="313",
    unit="fighters",
    metadata={"source": "test"},
)

print(stat.to_dict())

assert stat.to_dict()["value"] == "313"
assert stat.to_dict()["unit"] == "fighters"
assert stat.to_dict()["metadata"]["source"] == "test"


