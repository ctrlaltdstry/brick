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

## STATUS: DONE (2026-06-11) — build succeeded, AM confirmed working

The macOS build was completed on Mike's Apple Silicon Mac. The sections below
are updated with what ACTUALLY worked; the original assumptions that turned
out wrong are called out inline. Repeatable rebuild: `tools/build_native_mac.sh`.

## What you (the Mac-side Claude) need to do

### 1. External prerequisites — NONE need a download, both original assumptions were wrong
- **Full Xcode is NOT required.** The SDK's `macos_universal_xcode` preset
  needs it, but CMake's "Ninja Multi-Config" generator builds the SDK fine
  with just the Command Line Tools (`xcode-select --install`). Portable
  cmake (>= 3.30) + ninja from official binaries into `~/Dev/tools` —
  no Homebrew, no sign-in.
- **The macOS C++ SDK is NOT a portal download.** Maxon ships it inside the
  app: `/Applications/Maxon Cinema 4D 2026/sdk.zip` — guaranteed to match
  the installed build exactly. Unzip to `~/Dev/c4d_sdk_2026`.

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
Then build with the Ninja generator (NOT the `macos_universal_xcode` preset,
which requires full Xcode). The system frameworks must be passed as plain
linker flags — the SDK's own `FRAMEWORKS.OSX` plumbing emits compound
`"-framework Foo"` strings only the Xcode generator can parse:
```bash
cd ~/Dev/c4d_sdk_2026
FW="-framework CoreFoundation -framework Foundation -framework CoreServices \
-framework AppKit -framework CoreGraphics -framework IOKit -framework Security \
-framework SystemConfiguration"
cmake -S . -B _build_ninja -G "Ninja Multi-Config" -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_SHARED_LINKER_FLAGS="$FW" -DCMAKE_MODULE_LINKER_FLAGS="$FW"
cmake --build _build_ninja --config Release
```
The built `bricklibrary.inline_gui.xlib` (arm64 Mach-O bundle, ad-hoc
linker-signed — sufficient for local loading) lands under
`_build_ninja/bin/Release/plugins/bricklibrary.inline_gui/`.

All of the above is scripted in `tools/build_native_mac.sh`.

### 4. Install + verify
Copy the built `bricklibrary.inline_gui` bundle next to
`c4d_brick_generator.pyp` in the installed plugin folder (same nested layout
the Windows deploy uses). Restart C4D, drop a Cubify object → the Attribute
Manager should now populate, identical to Windows. To confirm the module
loaded without GUI poking: `lsof -p $(pgrep -x "Cinema 4D") | grep bricklibrary`.

See `native/bricklibrary.inline_gui/README.md` for more detail.

## Build errors hit on first build (2026-06-11) and their fixes
The original claim "the source itself should not need changes" was wrong —
clang is stricter than MSVC. Three fixes, all already applied:

1. **SDK cmake bug under Ninja** (patch the SDK extract; re-apply after any
   re-extract of sdk.zip): `cmake/sdk_compiler_helper.cmake` passes
   `"-Xarch_x86_64 -msse4.2"` as ONE quoted arg in the non-Xcode branch →
   clang errors `no such file or directory`. Split into separate args via a
   genex semicolon list:
   `"$<$<COMPILE_LANGUAGE:CXX>:-Xarch_x86_64;${MAXON_COMPILE_OPTIONS_MACOS_X64_ISA}>"`.
2. **`-Werror,-Wmissing-prototypes` in our source** (committed): the five
   file-local `Register*()` functions in `source/main.cpp` needed `static`
   (MSVC has no such warning, so Windows never caught it).
3. **Undefined CoreFoundation/AppKit symbols at link** — solved by the `$FW`
   linker flags above (the Maxon static libs reference them; the Xcode
   generator path links them implicitly).
