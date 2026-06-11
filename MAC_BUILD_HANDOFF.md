# macOS build handoff

Context for a Claude instance running on a **Mac** (e.g. in Cursor). The plugin
already runs on macOS — numpy/scipy load and bricks generate — but the **Cubify
object's Attribute Manager is EMPTY**. This file is the handoff so you don't
re-investigate from scratch.

## Root cause (already diagnosed, confirmed)

The object description `BrickGen/res/description/obrickifyassembly.res`
references two **custom GUIs** — `CUSTOMGUIBRICKSOURCES` (line ~170) and
`CUSTOMGUIBRICKLIBRARY` (line ~434) — implemented in the native C++ module
`native/bricklibrary.inline_gui/source/main.cpp`. That module previously had a
**Windows-only** build. When the custom GUIs aren't registered, C4D on macOS
**silently drops the entire object description → no parameters in the AM**
(geometry still works because it's pure Python). A separate, already-fixed issue
was non-ASCII em-dashes in the `.res` comments (now pure ASCII).

So: **the fix is to build `native/bricklibrary.inline_gui` for macOS** and
include it in the Mac plugin package. The source is platform-agnostic C4D SDK
code (no Windows-only APIs), and `projectdefinition.txt` already declares
`Platform=Win64;OSX;Linux`, so it should compile on macOS without source edits.

## What you (the Mac-side Claude) need to do

### 1. External prerequisites the user must install (you can guide, not download)
- **Xcode** + Command Line Tools (`xcode-select --install`).
- The **macOS Cinema 4D 2026 C++ SDK** from Maxon's developer portal
  (developers.maxon.net). The Windows SDK does NOT cross-compile a Mac plugin.

### 2. Vendor the macOS Python deps (so the plugin imports work locally)
`vendor/` is gitignored, so a fresh clone has no numpy/scipy. The Windows
`tools/vendor_mac_deps.ps1` is PowerShell; on a Mac just run the equivalent
`pip download` directly (pinned to match Windows: numpy 2.4.4, scipy 1.17.1):

```bash
python3 -m pip download --only-binary=:all: \
  --platform macosx_12_0_arm64 --python-version 3.11 --implementation cp --abi cp311 \
  --dest .vendor_wheels_arm64 "numpy==2.4.4" "scipy==1.17.1"
mkdir -p vendor/macos_arm64
for w in .vendor_wheels_arm64/*.whl; do unzip -o "$w" -d vendor/macos_arm64; done
rm -rf .vendor_wheels_arm64
```
(The plugin's `plugin_bootstrap.py` already picks `vendor/macos_arm64` on
Apple Silicon.)

### 3. Build the native module for macOS
Point the macOS C4D SDK's `custom_paths.txt` at this module (adjust path):
```
MODULE /Users/<you>/path/to/brick/native/bricklibrary.inline_gui
```
Then from the SDK root:
```bash
cd /path/to/c4d_sdk_2026
cmake --preset macos_universal_xcode
cmake --build --preset macos_universal_xcode --config Release
```
The built `bricklibrary.inline_gui` macOS plugin bundle lands under the SDK
build output `.../bin/Release/plugins/`.

### 4. Install + verify
Copy the built `bricklibrary.inline_gui` bundle next to
`c4d_brick_generator.pyp` in the installed plugin folder (same nested layout
the Windows deploy uses). Restart C4D, drop a Cubify object → the Attribute
Manager should now populate, identical to Windows.

See `native/bricklibrary.inline_gui/README.md` for more detail.

## If the build errors
Read `native/bricklibrary.inline_gui/source/main.cpp` and the SDK's CMake
config; common first-build issues are SDK-version/header mismatches or the
`custom_paths.txt` MODULE path. Fix and re-run; the source itself should not
need changes.
