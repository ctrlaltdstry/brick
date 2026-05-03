"""BrickIt source-child / polygon-island hierarchy grouping helpers."""
import re

import c4d

from source_geometry import placement_group_key


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_. -]+")


def _safe_name(value, fallback):
    name = str(value or fallback).strip()
    name = _SAFE_NAME_RE.sub("_", name)
    name = name.strip(" ._")
    return name or fallback


def _grouping_info(info):
    grouping = (info or {}).get("source_island_groups") or {}
    groups = {
        str(row.get("key")): row
        for row in list(grouping.get("groups") or [])
        if row.get("key") is not None
    }
    placement_groups = grouping.get("placement_groups") or {}
    return groups, placement_groups


def resolve_group_key(info, placement):
    """Return the best stored source-island group key for a placement."""
    groups, placement_groups = _grouping_info(info)
    if not groups or not placement_groups:
        return None
    key = placement_group_key(placement)
    direct = placement_groups.get(key)
    if direct in groups:
        return direct

    # Generated smooth-top caps are created after fitting, so they do not have
    # a direct metadata row. Reuse the nearest fitted placement at the same X/Z.
    x = int(getattr(placement, "x", 0))
    z = int(getattr(placement, "z", 0))
    y = int(getattr(placement, "y", 0))
    candidates = []
    for placement_key, group_key in placement_groups.items():
        if group_key not in groups:
            continue
        try:
            px, py, pz = int(placement_key[0]), int(placement_key[1]), int(placement_key[2])
        except Exception:
            continue
        if px == x and pz == z:
            candidates.append((abs(py - y), group_key))
    if candidates:
        return sorted(candidates, key=lambda row: row[0])[0][1]

    # Last resort for generated cosmetic placements: use the nearest fitted
    # placement group so no carrier is left loose under the top-level bricks
    # null. This keeps Make Editable organization predictable.
    nearest = []
    for placement_key, group_key in placement_groups.items():
        if group_key not in groups:
            continue
        try:
            px, py, pz = int(placement_key[0]), int(placement_key[1]), int(placement_key[2])
        except Exception:
            continue
        nearest.append((((px - x) * (px - x)) + ((pz - z) * (pz - z)), abs(py - y), group_key))
    if nearest:
        return sorted(nearest, key=lambda row: (row[0], row[1]))[0][2]
    return None


def _ungrouped_parent(root, cache):
    parent = cache.get("source:ungrouped")
    if parent is None:
        parent = c4d.BaseObject(c4d.Onull)
        parent.SetName("99_Ungrouped")
        parent.InsertUnder(root)
        cache["source:ungrouped"] = parent
    island = cache.get("island:ungrouped")
    if island is None:
        island = c4d.BaseObject(c4d.Onull)
        island.SetName("001_Ungrouped")
        island.InsertUnder(parent)
        cache["island:ungrouped"] = island
    return island


def grouped_parent_for_placement(info, placement, root, cache):
    """Return/create the parent null for a placement under `root`."""
    group_key = resolve_group_key(info, placement)
    if group_key is None:
        return _ungrouped_parent(root, cache)
    groups, _placement_groups = _grouping_info(info)
    row = groups.get(group_key)
    if row is None:
        return _ungrouped_parent(root, cache)

    source_key = "source:{0}".format(int(row.get("group_index", 0)))
    source_parent = cache.get(source_key)
    if source_parent is None:
        source_parent = c4d.BaseObject(c4d.Onull)
        source_parent.SetName(
            "{0:02d}_{1}".format(
                int(row.get("group_index", 0)) + 1,
                _safe_name(row.get("source_name"), "Source"),
            )
        )
        source_parent.InsertUnder(root)
        cache[source_key] = source_parent

    island_key = "island:{0}".format(group_key)
    island_parent = cache.get(island_key)
    if island_parent is None:
        island_parent = c4d.BaseObject(c4d.Onull)
        island_parent.SetName(
            "{0:03d}_{1}".format(
                int(row.get("island_index", 0)) + 1,
                _safe_name(row.get("island_name"), "Island"),
            )
        )
        island_parent.InsertUnder(source_parent)
        cache[island_key] = island_parent
    return island_parent
