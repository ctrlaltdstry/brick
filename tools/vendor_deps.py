#!/usr/bin/env python3
"""Fetch the vendored numpy/scipy for ALL platforms, from any machine.

The vendored deps are prebuilt PyPI wheels, so no Windows machine is needed
to fetch the Windows set (and vice versa) -- pip can download wheels for a
foreign platform. This replaces the per-OS vendor_c4d_deps.ps1 /
vendor_mac_deps.ps1 pair with one cross-platform script.

Pins match the C4D 2026 Python 3.11 runtime. Output layout (what
plugin_bootstrap.py expects):

    vendor/win_amd64/...
    vendor/macos_arm64/...

Usage:
    python3 tools/vendor_deps.py            # fetch any missing platform
    python3 tools/vendor_deps.py --force    # re-fetch everything
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(REPO_ROOT, "vendor")

PINS = ["numpy==2.4.4", "scipy==1.17.1"]

# vendor subdir -> pip --platform tag(s) to try, newest first.
PLATFORMS = {
    "win_amd64": ["win_amd64"],
    "macos_arm64": ["macosx_12_0_arm64", "macosx_11_0_arm64"],
}


def fetch(subdir, pip_platforms):
    dest = os.path.join(VENDOR, subdir)
    with tempfile.TemporaryDirectory(prefix="vendor_wheels_") as tmp:
        last_err = None
        for tag in pip_platforms:
            cmd = [
                sys.executable, "-m", "pip", "download",
                "--only-binary=:all:",
                "--platform", tag,
                "--python-version", "3.11",
                "--implementation", "cp",
                "--abi", "cp311",
                "--dest", tmp,
                *PINS,
            ]
            print(f"[{subdir}] pip download --platform {tag} ...")
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                break
            last_err = res.stderr.strip().splitlines()[-1] if res.stderr else "?"
        else:
            raise SystemExit(f"[{subdir}] pip download failed: {last_err}")

        if os.path.isdir(dest):
            shutil.rmtree(dest)
        os.makedirs(dest)
        for name in sorted(os.listdir(tmp)):
            if not name.endswith(".whl"):
                continue
            print(f"[{subdir}] unpacking {name}")
            with zipfile.ZipFile(os.path.join(tmp, name)) as zf:
                zf.extractall(dest)
    print(f"[{subdir}] done -> {dest}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="re-fetch even if present")
    ap.add_argument(
        "--platform", choices=sorted(PLATFORMS), action="append",
        help="limit to specific platform(s); default: all",
    )
    args = ap.parse_args()

    selected = args.platform or sorted(PLATFORMS)
    for subdir in selected:
        dest = os.path.join(VENDOR, subdir)
        if os.path.isdir(dest) and not args.force:
            print(f"[{subdir}] already present, skipping (--force to refresh)")
            continue
        fetch(subdir, PLATFORMS[subdir])


if __name__ == "__main__":
    main()
