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


_LOOKUP_CACHE_KEY = "__grouping_lookup__"


def _build_grouping_lookup(info):
    """Parse `info` once into structures suitable for O(1)/O(K) lookups.

    `grouped_parent_for_placement` is called once per placement (often
    700-2000+ times during Create Proxies and the integrated MoGraph
    rebuild). Re-walking `info["source_island_groups"]` and rebuilding the
    `groups` dict on every call previously made the loop quadratic for
    generated smooth-top caps. This builds:

      groups          {group_key: row}
      placement_groups{(x, y, z, ...): group_key}      (raw map)
      by_xz           {(x, z): [(y, group_key), ...]}  (cap-fallback index)
      flat            [(px, py, pz, group_key), ...]   (spatial-nearest scan)

    `flat` is iterated only when neither the direct lookup nor the same-XZ
    column finds a match — generally a rare last-resort path.
    """
    grouping = (info or {}).get("source_island_groups") or {}
    groups = {
        str(row.get("key")): row
        for row in list(grouping.get("groups") or [])
        if row.get("key") is not None
    }
    placement_groups = grouping.get("placement_groups") or {}
    by_xz = {}
    flat = []
    for placement_key, group_key in placement_groups.items():
        if group_key not in groups:
            continue
        try:
            px, py, pz = int(placement_key[0]), int(placement_key[1]), int(placement_key[2])
        except Exception:
            continue
        by_xz.setdefault((px, pz), []).append((py, group_key))
        flat.append((px, py, pz, group_key))
    return {
        "groups": groups,
        "placement_groups": placement_groups,
        "by_xz": by_xz,
        "flat": flat,
    }


def _get_lookup(info, cache):
    """Return the cached grouping lookup, building it on the first call."""
    if cache is None:
        return _build_grouping_lookup(info)
    lookup = cache.get(_LOOKUP_CACHE_KEY)
    if lookup is None:
        lookup = _build_grouping_lookup(info)
        cache[_LOOKUP_CACHE_KEY] = lookup
    return lookup


def _grouping_info(info):
    """Back-compat shim — uncached parse of `info`. Prefer `_get_lookup`."""
    lookup = _build_grouping_lookup(info)
    return lookup["groups"], lookup["placement_groups"]


def _resolve_group_key_with_lookup(lookup, placement):
    groups = lookup["groups"]
    placement_groups = lookup["placement_groups"]
    if not groups or not placement_groups:
        return None
    key = placement_group_key(placement)
    direct = placement_groups.get(key)
    if direct in groups:
        return direct

    # Generated smooth-top caps are created after fitting, so they do not have
    # a direct metadata row. Reuse the nearest fitted placement at the same
    # X/Z column — O(K) where K is the placements at that column.
    x = int(getattr(placement, "x", 0))
    z = int(getattr(placement, "z", 0))
    y = int(getattr(placement, "y", 0))
    column = lookup["by_xz"].get((x, z))
    if column:
        return min(column, key=lambda row: abs(row[0] - y))[1]

    # Last resort: nearest fitted placement anywhere in the XZ plane. Only
    # reached when neither the direct map nor the same-XZ column matches.
    flat = lookup["flat"]
    if not flat:
        return None
    best = None
    best_d2 = None
    best_dy = None
    for px, py, pz, group_key in flat:
        d2 = (px - x) * (px - x) + (pz - z) * (pz - z)
        dy = abs(py - y)
        if best_d2 is None or d2 < best_d2 or (d2 == best_d2 and dy < best_dy):
            best_d2 = d2
            best_dy = dy
            best = group_key
    return best


def resolve_group_key(info, placement):
    """Return the best stored source-island group key for a placement.

    This is the uncached entry point used outside the inner Create Proxies /
    MoGraph build loop. The hot loop calls `grouped_parent_for_placement`,
    which uses a cached lookup keyed off the same `cache` dict callers pass
    in for parent Nulls.
    """
    return _resolve_group_key_with_lookup(_build_grouping_lookup(info), placement)


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
    """Return/create the parent null for a placement under `root`.

    The grouping lookup parsed from `info` is cached on the same `cache`
    dict that holds the per-source/per-island parent Nulls — re-parsing on
    every per-placement call previously made this O(N²) for ~700+ bricks.
    """
    lookup = _get_lookup(info, cache)
    group_key = _resolve_group_key_with_lookup(lookup, placement)
    if group_key is None:
        return _ungrouped_parent(root, cache)
    row = lookup["groups"].get(group_key)
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
