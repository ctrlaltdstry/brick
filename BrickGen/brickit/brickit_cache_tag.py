"""Cubify Cache tag — passive store for the per-frame fit cache.

Auto-created by the Cubify object's "Bake Fit Cache" action; it holds the
serialized per-frame brick layouts in a hidden string param so they persist
with the scene. The Cubify generator reads this tag during GetVirtualObjects
(a plain data read — no Execute), and when the tag is present + Enabled it
plays the cached reflow. Registered with TAG_VISIBLE only (NO TAG_EXPRESSION),
so it has no per-frame Execute() and adds zero evaluation cost.
"""
import c4d
from c4d import plugins

from c4d_symbols import (
    CUBIFY_CACHE_ENABLED,
    CUBIFY_CACHE_BLOB,
    CUBIFY_CACHE_INFO,
)


class CubifyCacheTag(plugins.TagData):
    def Init(self, node, isCloneInit=False):
        try:
            node[CUBIFY_CACHE_ENABLED] = True
            node[CUBIFY_CACHE_BLOB] = ""
            node[CUBIFY_CACHE_INFO] = "Empty — run Bake Fit Cache"
        except Exception:
            pass
        return True
