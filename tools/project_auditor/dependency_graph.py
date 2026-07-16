def build_dependency_graph(modules):

    graph = {}

    for module_name, info in modules.items():

        graph[module_name] = sorted(info.imports)

    return graph