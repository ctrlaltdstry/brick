"""Bootstrap and logging helpers shared by BrickGen plugin modules."""
import importlib
import os
import site
import sys
import tempfile
import time
import webbrowser

import c4d


BRICK_LOG_PATH = os.path.join(tempfile.gettempdir(), "brickgen.log")
USER_MANUAL_FALLBACK_URL = (
    "https://github.com/ctrlaltdstry/brick/blob/main/USER_MANUAL.html"
)


def open_user_manual():
    """Open the bundled USER_MANUAL.html in the user's default browser.

    Looks for the HTML file alongside the deployed plugin first (so end
    users get a fully-offline experience), then falls back to the canonical
    GitHub URL if the local file is missing.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "USER_MANUAL.html"),
        os.path.join(here, "..", "USER_MANUAL.html"),
        os.path.join(here, "..", "..", "USER_MANUAL.html"),
    ]
    for path in candidates:
        try:
            normalized = os.path.normpath(path)
            if os.path.isfile(normalized):
                webbrowser.open("file:///" + normalized.replace("\\", "/"))
                return True
        except Exception:
            continue
    try:
        webbrowser.open(USER_MANUAL_FALLBACK_URL)
        return True
    except Exception:
        return False


def brick_log(message):
    """Mirror plugin diagnostics to C4D console and a file Cursor can read."""
    text = str(message)
    try:
        c4d.GePrint(text)
    except Exception:
        try:
            print(text)
        except Exception:
            pass
    try:
        if os.path.exists(BRICK_LOG_PATH) and os.path.getsize(BRICK_LOG_PATH) > 2 * 1024 * 1024:
            os.remove(BRICK_LOG_PATH)
        with open(BRICK_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write("{0} {1}\n".format(time.strftime("%Y-%m-%d %H:%M:%S"), text))
    except Exception:
        pass


def ensure_brick_on_path():
    """Make sure the brick package is importable."""
    here = os.path.dirname(os.path.abspath(__file__))

    candidates = []
    env_root = os.environ.get("BRICK_ROOT")
    if env_root:
        candidates.append(env_root)

    # Prefer a bundled `brick/` package beside the installed plugin before
    # falling back to development paths.
    walk = here
    for _ in range(6):
        vendor_dir = os.path.join(walk, "vendor")
        if os.path.isdir(vendor_dir):
            candidates.append(vendor_dir)
        pkg_init = os.path.join(walk, "brick", "__init__.py")
        if os.path.isfile(pkg_init):
            candidates.append(walk)
        parent = os.path.dirname(walk)
        if parent == walk:
            break
        walk = parent
    candidates.append(here)

    # Development fallback for local, unpackaged runs.
    candidates.append(r"Z:\02_MKE\2026\BRICK\brick")

    try:
        candidates.extend(site.getsitepackages())
    except Exception:
        pass
    try:
        candidates.append(site.getusersitepackages())
    except Exception:
        pass
    appdata = os.environ.get("APPDATA")
    if appdata:
        py_tag = "Python{0}{1}".format(
            sys.version_info.major, sys.version_info.minor
        )
        candidates.append(os.path.join(appdata, "Python", py_tag, "site-packages"))

    ordered = []
    seen = set()
    for p in candidates:
        if not p:
            continue
        p_norm = os.path.normcase(os.path.normpath(p))
        if p_norm in seen:
            continue
        if not os.path.isdir(p):
            continue
        seen.add(p_norm)
        ordered.append(p)

    for p in reversed(ordered):
        while p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)


def reload_brick_modules():
    """Hot-reload every loaded brick module."""
    ensure_brick_on_path()
    names = [
        n for n in list(sys.modules.keys())
        if n == "brick" or n.startswith("brick.")
    ]
    names.sort(key=lambda n: -n.count("."))
    for n in names:
        mod = sys.modules.get(n)
        if mod is None:
            continue
        try:
            importlib.reload(mod)
        except Exception as exc:
            brick_log("[brick] reload failed for {0}: {1}".format(n, exc))
            sys.modules.pop(n, None)
