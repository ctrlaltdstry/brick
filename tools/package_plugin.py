#!/usr/bin/env python3
"""Build the Cubit distribution package (cross-platform; replaces package_plugin.ps1).

Layout:

    dist/Cubit <version>/
        MacOS/
            Cubit/                  <- drop into the C4D plugins folder (Mac)
                c4d_brick_generator.pyp, brick/, res/, ...
                bricklibrary.inline_gui/   (mac .xlib)
                vendor/macos_arm64/ [+ macos_x86_64/]
        Windows/
            Cubit/                  <- drop into the C4D plugins folder (Windows)
                ... same, with the .xdl64 native build + vendor/win_amd64/

    dist/Cubit <version>.zip        (with --zip)

Version defaults to the latest git tag (v1.1.0 -> "1.1.0"); override with
--version. Each platform half warns loudly if its native GUI or vendor deps
can't be found -- the native GUI is REQUIRED at runtime (without it C4D drops
the Cubify object description and the Attribute Manager is empty).

Typical use:
    python3 tools/package_plugin.py --zip                 # both platforms
    python3 tools/package_plugin.py --platform mac --zip  # mac half only
"""
import argparse
import os
import shutil
import subprocess
import sys
from glob import glob

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NATIVE_GUI_NAME = "bricklibrary.inline_gui"

# Mirrors the strip filters of the old package_plugin.ps1.
DIR_FILTERS = {
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git",
    ".cursor", ".claude", "tools", "tests", "backup", "demo", "docs",
    "output", "output_alt", "output_greedy", "output_uniform",
}
FILE_FILTERS = (".pyc", ".pyo", ".log", ".tmp", ".bak", ".pdb")


def latest_git_tag():
    try:
        tag = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=REPO_ROOT, text=True,
        ).strip()
        return tag.lstrip("v")
    except Exception:
        return None


def first_existing(paths):
    for p in paths:
        if p and os.path.isdir(p):
            return p
    return None


def installed_plugin_dirs():
    """Installed Cubit plugin folders, used as fallback artifact sources."""
    if sys.platform == "darwin":
        pattern = os.path.expanduser(
            "~/Library/Preferences/Maxon/Maxon Cinema 4D 2026*/plugins/Cubit*"
        )
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        pattern = os.path.join(appdata, "Maxon", "Maxon Cinema 4D 2026*", "plugins", "Cubit*")
    else:
        return []
    return sorted(glob(pattern), key=os.path.getmtime, reverse=True)


def native_gui_candidates(os_key):
    # Committed builds in the repo come first: they let EITHER machine package
    # both platforms. native_stamp.py guards them against source drift.
    builds = os.path.join(REPO_ROOT, "native", "builds")
    if os_key == "mac":
        cands = [
            os.environ.get("BRICK_NATIVE_GUI_MAC_SOURCE"),
            os.path.join(builds, "macos_arm64", NATIVE_GUI_NAME),
        ]
        cands.append(os.path.expanduser(
            "~/Dev/c4d_sdk_2026/_build_ninja/bin/Release/plugins/" + NATIVE_GUI_NAME
        ))
    else:
        cands = [
            os.environ.get("BRICK_NATIVE_GUI_WIN_SOURCE"),
            os.environ.get("BRICK_NATIVE_GUI_SOURCE"),  # legacy ps1 name
            os.path.join(builds, "win64", NATIVE_GUI_NAME),
            "C:/Dev/c4d_sdk_2026/build-win64/bin/Release/plugins/" + NATIVE_GUI_NAME,
        ]
    # Last resort: a native module nested in an installed plugin of the
    # matching platform (only ever the host OS's own install).
    if (os_key == "mac") == (sys.platform == "darwin"):
        for plug in installed_plugin_dirs():
            cands.append(os.path.join(plug, NATIVE_GUI_NAME))
    return cands


def vendor_sources(os_key):
    """(subdir-name, source-path-candidates) pairs for this platform."""
    vendor = os.path.join(REPO_ROOT, "vendor")
    if os_key == "mac":
        pairs = []
        for sub in ("macos_arm64", "macos_x86_64"):
            cands = [os.path.join(vendor, sub)]
            if sys.platform == "darwin":
                cands += [os.path.join(p, "vendor", sub) for p in installed_plugin_dirs()]
            pairs.append((sub, cands))
        return pairs
    return [("win_amd64", [
        os.path.join(vendor, "win_amd64"),
        # Legacy flat layout: vendor/ holding the Windows numpy/scipy directly.
        vendor if os.path.isdir(os.path.join(vendor, "numpy")) else None,
    ])]


def strip_dev_content(root):
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        for d in list(dirnames):
            if d in DIR_FILTERS:
                shutil.rmtree(os.path.join(dirpath, d))
                dirnames.remove(d)
        for f in filenames:
            if f.endswith(FILE_FILTERS):
                os.remove(os.path.join(dirpath, f))


def build_platform(os_key, os_folder, package_root, plugin_name, warnings):
    plugin_dir = os.path.join(package_root, os_folder, plugin_name)
    os.makedirs(os.path.dirname(plugin_dir), exist_ok=True)

    shutil.copytree(os.path.join(REPO_ROOT, "BrickGen"), plugin_dir)
    shutil.copytree(os.path.join(REPO_ROOT, "brick"), os.path.join(plugin_dir, "brick"))

    # Vendored numpy/scipy (platform-specific native binaries).
    got_vendor = False
    for sub, cands in vendor_sources(os_key):
        src = first_existing(cands)
        if src:
            shutil.copytree(src, os.path.join(plugin_dir, "vendor", sub))
            print(f"  [{os_folder}] vendor/{sub} <- {src}")
            got_vendor = got_vendor or sub != "macos_x86_64"
    if not got_vendor:
        warnings.append(
            f"{os_folder}: no vendored numpy/scipy found -- plugin will not "
            f"import. Run: python3 tools/vendor_deps.py"
        )

    # Native custom-GUI module. REQUIRED: without it C4D silently drops the
    # Cubify object description -> empty Attribute Manager.
    native = first_existing(native_gui_candidates(os_key))
    if native:
        shutil.copytree(native, os.path.join(plugin_dir, NATIVE_GUI_NAME))
        print(f"  [{os_folder}] {NATIVE_GUI_NAME} <- {native}")
        # Staleness guard for stamped (repo-committed) builds: warn if the
        # C++ source changed since this binary was built.
        if os.path.isfile(os.path.join(native, "build_info.txt")):
            import native_stamp
            ok, msg = native_stamp.check(native)
            if not ok:
                warnings.append(f"{os_folder}: {msg}")
    else:
        if os_key == "mac":
            hint = ("run tools/build_native_mac.sh (also refreshes "
                    "native/builds/macos_arm64), or set BRICK_NATIVE_GUI_MAC_SOURCE")
        else:
            hint = ("on the Windows machine: build per native/.../README.md, copy "
                    "the built folder to native/builds/win64/, stamp it with "
                    "`python tools/native_stamp.py write native/builds/win64/"
                    + NATIVE_GUI_NAME + "`, and commit")
        warnings.append(
            f"{os_folder}: native {NATIVE_GUI_NAME} not found -- the Cubify "
            f"Attribute Manager will be EMPTY. To fix: {hint}."
        )

    for doc in ("README_INSTALL.md", "USER_MANUAL.html"):
        src = os.path.join(REPO_ROOT, doc)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(plugin_dir, doc))

    strip_dev_content(plugin_dir)

    # macOS: drop the double-click installer beside the Cubit folder. It copies
    # Cubit into the C4D plugins folder AND strips the download (quarantine)
    # flag, so the user doesn't hit Gatekeeper's "cannot verify malware"
    # warning on the unsigned native binaries (.xlib + numpy/scipy .so).
    if os_key == "mac":
        installer = os.path.join(REPO_ROOT, "tools", "templates", "Install Cubit (Mac).command")
        if os.path.isfile(installer):
            dst = os.path.join(os.path.dirname(plugin_dir), "Install Cubit (Mac).command")
            shutil.copy2(installer, dst)
            os.chmod(dst, 0o755)
            print(f"  [{os_folder}] installer <- {installer}")
        else:
            warnings.append(f"{os_folder}: installer template missing at {installer}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--version", help="package version (default: latest git tag)")
    ap.add_argument("--platform", choices=("all", "mac", "win"), default="all")
    ap.add_argument("--zip", action="store_true", help="also write dist/Cubit <version>.zip")
    ap.add_argument("--sign", action="store_true",
                    help="sign + notarize the macOS binaries (needs a Developer ID "
                         "cert + 'cubit-notary' profile; see SIGNING_SETUP.md)")
    args = ap.parse_args()

    version = args.version or latest_git_tag()
    if not version:
        ap.error("no git tag found; pass --version")

    name = f"Cubit {version}"
    # The OUTER dir + zip are versioned (so the download is clearly labeled),
    # but the INNER plugin folder is plain "Cubit" so it drops straight into
    # the C4D plugins folder as plugins/Cubit/ (not plugins/Cubit <version>/).
    plugin_name = "Cubit"
    dist = os.path.join(REPO_ROOT, "dist")
    package_root = os.path.join(dist, name)
    if os.path.isdir(package_root):
        shutil.rmtree(package_root)
    os.makedirs(package_root, exist_ok=True)

    targets = {"mac": ("mac", "MacOS"), "win": ("win", "Windows")}
    selected = ("mac", "win") if args.platform == "all" else (args.platform,)

    warnings = []
    for key in selected:
        os_key, os_folder = targets[key]
        print(f"Packaging {os_folder}/{plugin_name} ...")
        build_platform(os_key, os_folder, package_root, plugin_name, warnings)

    readme = os.path.join(REPO_ROOT, "README_INSTALL.md")
    if os.path.isfile(readme):
        shutil.copy2(readme, os.path.join(package_root, "README_INSTALL.md"))

    # Sign + notarize the macOS payload BEFORE zipping, so the shipped zip
    # carries signed binaries. No-op for win-only builds.
    if args.sign and "mac" in selected:
        mac_cubit = os.path.join(package_root, "MacOS", plugin_name)
        signer = os.path.join(REPO_ROOT, "tools", "sign_notarize_mac.sh")
        print("Signing + notarizing macOS binaries ...")
        try:
            subprocess.run([signer, mac_cubit], check=True)
        except subprocess.CalledProcessError:
            warnings.append(
                "MacOS: signing/notarization failed (see output above). The "
                "package was still written UNSIGNED -- ship it with the "
                "Install Cubit (Mac).command installer, or fix signing and "
                "re-run with --sign."
            )

    if args.zip:
        zip_base = os.path.join(dist, name)
        if os.path.isfile(zip_base + ".zip"):
            os.remove(zip_base + ".zip")
        shutil.make_archive(zip_base, "zip", root_dir=dist, base_dir=name)
        print(f"Wrote zip: {zip_base}.zip")

    print(f"Wrote package: {package_root}")
    if warnings:
        print("\nWARNINGS:")
        for w in warnings:
            print(f"  ! {w}")
        sys.exit(1 if args.platform != "all" else 0)


if __name__ == "__main__":
    main()
