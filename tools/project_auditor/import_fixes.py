REPLACEMENTS = {

    "knowledge_extraction_v2":
        "knowledge_v2",

}


def build_import_fixes(missing):

    fixes = {}

    for module, imports in missing.items():

        suggestions = []

        for imp in imports:

            fixed = imp

            for old, new in REPLACEMENTS.items():

                if old in fixed:
                    fixed = fixed.replace(old, new)

            suggestions.append({
                "missing": imp,
                "suggested": fixed
            })

        fixes[module] = suggestions

    return fixes