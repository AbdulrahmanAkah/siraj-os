def normalize_import(module):

    if not module:
        return ""

    module = module.replace("\\", "/")
    module = module.replace("/", ".")

    if module.endswith(".py"):
        module = module[:-3]

    while ".." in module:
        module = module.replace("..", ".")

    return module.strip(".")


def build_import_index(modules):

    result = {}

    for module_name, info in modules.items():

        result[module_name] = sorted(
            normalize_import(i)
            for i in info.imports
            if normalize_import(i)
        )

    return result


def detect_missing_imports(modules):

    existing = set(modules.keys())

    missing = {}

    prefixes = (
        "application",
        "domain",
        "core",
        "infrastructure",
    )

    for module_name, info in modules.items():

        bad = []

        for imp in info.imports:

            imp = normalize_import(imp)

            if not imp:
                continue

            if imp.startswith(prefixes):
                imp = "src." + imp

            if imp.startswith("src.") and imp not in existing:
                bad.append(imp)

        if bad:
            missing[module_name] = sorted(set(bad))

    return missing
