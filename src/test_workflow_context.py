from src.application.workflow.workflow_context import WorkflowContext

ctx = WorkflowContext("Battle of Badr")

print(ctx.to_dict())

assert ctx.topic == "Battle of Badr"
assert ctx.outline is None
assert ctx.script is None
assert ctx.scenes is None

ctx.metadata["version"] = 1

assert ctx.metadata["version"] == 1

print("WorkflowContext OK")


