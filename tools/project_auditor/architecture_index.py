from pathlib import Path


LAYERS = (
    "application",
    "domain",
    "core",
    "infrastructure",
    "cli",
)


def build_architecture_index(modules):

    result = {}

    for module in sorted(modules):

        layer = "unknown"

        for l in LAYERS:

            if module.startswith("src." + l):
                layer = l
                break

        result[module] = {
            "layer": layer,
            "path": module.replace(".", "/") + ".py"
        }

    return result