from datetime import datetime


def build_statistics(modules):

    return {

        "generated": datetime.now().isoformat(),

        "files": len(modules),

        "classes": sum(
            len(m.classes)
            for m in modules.values()
        ),

        "functions": sum(
            len(m.functions)
            for m in modules.values()
        ),

        "imports": sum(
            len(m.imports)
            for m in modules.values()
        )

    }