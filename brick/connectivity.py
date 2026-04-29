"""Structural connectivity analysis for brick assemblies.

Two bricks are *coupled* if one sits directly on top of the other and
their footprints share at least one stud-cell. We build the coupling
graph and check that the whole assembly forms a single connected
component, since a real LEGO build needs to be one rigid piece.

We also report *articulation points* (single bricks whose removal would
split the model in two), which are weak spots a real build would benefit
from being engineered out.
"""
from typing import List, Tuple, Set, Dict
from collections import defaultdict, deque
from .fitter import BrickPlacement


def _footprints_overlap(p: BrickPlacement, q: BrickPlacement) -> bool:
    return not (
        p.x + p.w <= q.x or q.x + q.w <= p.x or
        p.z + p.d <= q.z or q.z + q.d <= p.z
    )


def build_coupling_graph(placements: List[BrickPlacement]) -> Dict[int, Set[int]]:
    """Edge from i to j iff brick j sits directly on i (or vice versa)
    AND their footprints overlap by at least one stud-cell."""
    graph: Dict[int, Set[int]] = defaultdict(set)
    # bucket placements by their bottom Y level to avoid n^2 over the whole list
    by_bottom: Dict[int, List[int]] = defaultdict(list)
    by_top: Dict[int, List[int]] = defaultdict(list)
    for i, p in enumerate(placements):
        by_bottom[p.y].append(i)
        by_top[p.y + p.h].append(i)

    for top_y, ids_below in by_top.items():
        # bricks whose top is at top_y: these support bricks whose bottom is at top_y
        for j in by_bottom.get(top_y, []):
            q = placements[j]
            for i in ids_below:
                p = placements[i]
                if _footprints_overlap(p, q):
                    graph[i].add(j)
                    graph[j].add(i)
    # ensure all nodes appear
    for i in range(len(placements)):
        graph[i]  # touch
    return dict(graph)


def connected_components(graph: Dict[int, Set[int]], n: int) -> List[List[int]]:
    seen = [False] * n
    comps = []
    for start in range(n):
        if seen[start]:
            continue
        comp = []
        q = deque([start])
        seen[start] = True
        while q:
            v = q.popleft()
            comp.append(v)
            for nb in graph.get(v, ()):
                if not seen[nb]:
                    seen[nb] = True
                    q.append(nb)
        comps.append(comp)
    return sorted(comps, key=lambda c: -len(c))


def find_articulation_points(graph: Dict[int, Set[int]], n: int) -> List[int]:
    """Standard Tarjan articulation-point DFS."""
    visited = [False] * n
    disc = [0] * n
    low = [0] * n
    parent = [-1] * n
    is_ap = [False] * n
    timer = [0]

    def dfs(u: int):
        children = 0
        visited[u] = True
        disc[u] = low[u] = timer[0]
        timer[0] += 1
        for v in graph.get(u, ()):
            if not visited[v]:
                parent[v] = u
                children += 1
                dfs(v)
                low[u] = min(low[u], low[v])
                if parent[u] == -1 and children > 1:
                    is_ap[u] = True
                if parent[u] != -1 and low[v] >= disc[u]:
                    is_ap[u] = True
            elif v != parent[u]:
                low[u] = min(low[u], disc[v])

    import sys
    sys.setrecursionlimit(max(10000, n * 4))
    for i in range(n):
        if not visited[i]:
            dfs(i)
    return [i for i in range(n) if is_ap[i]]


def check_connectivity(placements: List[BrickPlacement]) -> dict:
    """Returns a report dict with components and articulation points."""
    n = len(placements)
    graph = build_coupling_graph(placements)
    comps = connected_components(graph, n)
    aps = find_articulation_points(graph, n) if n else []
    return {
        "graph": graph,
        "components": comps,
        "n_components": len(comps),
        "largest_component_size": len(comps[0]) if comps else 0,
        "articulation_points": aps,
        "n_articulation_points": len(aps),
    }


def prune_to_largest_component(
    placements: List[BrickPlacement],
) -> Tuple[List[BrickPlacement], List[BrickPlacement]]:
    """Returns (kept, dropped) so the kept set is single-component buildable."""
    if not placements:
        return [], []
    report = check_connectivity(placements)
    if report["n_components"] <= 1:
        return list(placements), []
    keep = set(report["components"][0])
    kept = [p for i, p in enumerate(placements) if i in keep]
    dropped = [p for i, p in enumerate(placements) if i not in keep]
    return kept, dropped
