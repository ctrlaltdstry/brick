"""Structural connectivity analysis for brick assemblies.

Two bricks are *coupled* if one sits directly on top of the other and
their footprints share at least one stud-cell. We build the coupling
graph and check that the whole assembly forms a single connected
component, since a real LEGO build needs to be one rigid piece.

We also report *articulation points* (single bricks whose removal would
split the model in two), which are weak spots a real build would benefit
from being engineered out.
"""
from typing import Any, List, Tuple, Set, Dict
from collections import defaultdict, deque
from .fitter import BrickPlacement


def _footprint_overlap_cells(p: BrickPlacement, q: BrickPlacement) -> int:
    x_overlap = min(p.x + p.w, q.x + q.w) - max(p.x, q.x)
    z_overlap = min(p.z + p.d, q.z + q.d) - max(p.z, q.z)
    if x_overlap <= 0 or z_overlap <= 0:
        return 0
    return int(x_overlap * z_overlap)


def build_support_graph(
    placements: List[BrickPlacement],
) -> Tuple[Dict[int, Set[int]], Dict[int, Set[int]], List[Dict[str, int]]]:
    """Return directed bottom-to-top support edges and their clutch counts."""
    supports: Dict[int, Set[int]] = defaultdict(set)
    supported_by: Dict[int, Set[int]] = defaultdict(set)
    clutch_edges: List[Dict[str, int]] = []
    by_bottom: Dict[int, List[int]] = defaultdict(list)
    by_top: Dict[int, List[int]] = defaultdict(list)
    for i, p in enumerate(placements):
        by_bottom[p.y].append(i)
        by_top[p.y + p.h].append(i)

    for top_y, ids_below in by_top.items():
        for j in by_bottom.get(top_y, []):
            q = placements[j]
            for i in ids_below:
                p = placements[i]
                studs = _footprint_overlap_cells(p, q)
                if studs <= 0:
                    continue
                supports[i].add(j)
                supported_by[j].add(i)
                clutch_edges.append({
                    "below": int(i),
                    "above": int(j),
                    "studs": int(studs),
                })

    for i in range(len(placements)):
        supports[i]
        supported_by[i]
    return dict(supports), dict(supported_by), clutch_edges


def build_coupling_graph(placements: List[BrickPlacement]) -> Dict[int, Set[int]]:
    """Edge from i to j iff brick j sits directly on i (or vice versa)
    AND their footprints overlap by at least one stud-cell."""
    graph: Dict[int, Set[int]] = defaultdict(set)
    supports, _, _ = build_support_graph(placements)
    for i, ids_above in supports.items():
        for j in ids_above:
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


def _same_layer_islands(placements: List[BrickPlacement]) -> List[Dict[str, Any]]:
    by_layer: Dict[int, List[int]] = defaultdict(list)
    for i, p in enumerate(placements):
        by_layer[p.y].append(i)

    islands: List[Dict[str, Any]] = []
    for y, ids in sorted(by_layer.items()):
        if len(ids) <= 1:
            continue
        graph: Dict[int, Set[int]] = defaultdict(set)
        cell_owner: Dict[Tuple[int, int], int] = {}
        for i in ids:
            graph[i]
            p = placements[i]
            for x in range(p.x, p.x + p.w):
                for z in range(p.z, p.z + p.d):
                    cell_owner[(x, z)] = i
        for i in ids:
            p = placements[i]
            for x in range(p.x, p.x + p.w):
                for nz in (p.z - 1, p.z + p.d):
                    j = cell_owner.get((x, nz))
                    if j is not None and j != i:
                        graph[i].add(j)
                        graph[j].add(i)
            for z in range(p.z, p.z + p.d):
                for nx in (p.x - 1, p.x + p.w):
                    j = cell_owner.get((nx, z))
                    if j is not None and j != i:
                        graph[i].add(j)
                        graph[j].add(i)
        seen: Set[int] = set()
        for start in ids:
            if start in seen:
                continue
            stack = [start]
            seen.add(start)
            comp: List[int] = []
            while stack:
                cur = stack.pop()
                comp.append(cur)
                for nb in graph.get(cur, ()):
                    if nb not in seen:
                        seen.add(nb)
                        stack.append(nb)
            if len(comp) > 1:
                islands.append({
                    "y": int(y),
                    "indices": sorted(int(i) for i in comp),
                    "size": int(len(comp)),
                })
    return islands


def check_buildability(placements: List[BrickPlacement]) -> dict:
    """Report real bottom-to-top clutch buildability for placements.

    A placement is grounded when it starts on y=0, or when it is connected to
    such a base placement through directed support edges. Same-layer side
    contact is reported for diagnostics, but it is never a structural edge.
    """
    n = len(placements)
    graph = build_coupling_graph(placements)
    components = connected_components(graph, n)
    supports, supported_by, clutch_edges = build_support_graph(placements)
    base_indices = sorted(i for i, p in enumerate(placements) if p.y == 0)

    grounded: Set[int] = set(base_indices)
    q = deque(base_indices)
    while q:
        cur = q.popleft()
        for above in supports.get(cur, ()):
            if above not in grounded:
                grounded.add(above)
                q.append(above)

    ungrounded = sorted(i for i in range(n) if i not in grounded)
    unsupported = sorted(
        i for i, p in enumerate(placements)
        if p.y > 0 and not supported_by.get(i)
    )
    grounded_components = []
    floating_components = []
    for comp in components:
        row = sorted(int(i) for i in comp)
        if any(i in grounded for i in comp):
            grounded_components.append(row)
        else:
            floating_components.append(row)

    return {
        "buildable": bool(n == 0 or (not ungrounded and len(components) <= 1)),
        "single_component": bool(len(components) <= 1),
        "graph": graph,
        "support_graph": supports,
        "supported_by": supported_by,
        "clutch_edges": clutch_edges,
        "components": components,
        "n_components": int(len(components)),
        "base_indices": base_indices,
        "grounded_indices": sorted(int(i) for i in grounded),
        "ungrounded_indices": ungrounded,
        "unsupported_indices": unsupported,
        "n_ungrounded": int(len(ungrounded)),
        "n_unsupported": int(len(unsupported)),
        "grounded_components": grounded_components,
        "floating_components": floating_components,
        "n_grounded_components": int(len(grounded_components)),
        "n_floating_components": int(len(floating_components)),
        "same_layer_islands": _same_layer_islands(placements),
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
