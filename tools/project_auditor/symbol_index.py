from collections import defaultdict


def build_symbol_index(modules):

    classes = defaultdict(list)
    functions = defaultdict(list)

    for module_name, info in modules.items():

        # ignore archived modules
        if module_name.startswith("archive"):
            continue

        for c in info.classes:
            classes[c].append(module_name)

        for f in info.functions:
            functions[f].append(module_name)

    duplicates = {
        name: locations
        for name, locations in classes.items()
        if len(locations) > 1
    }

    function_duplicates = {
        name: locations
        for name, locations in functions.items()
        if len(locations) > 1
    }

    return {
        "classes": dict(classes),
        "functions": dict(functions),
        "duplicate_classes": duplicates,
        "duplicate_functions": function_duplicates,
    }
