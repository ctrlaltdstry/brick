#!/bin/zsh
# Build + install the native bricklibrary.inline_gui module for macOS.
# Mac counterpart to the Windows flow in native/bricklibrary.inline_gui/README.md
# and the native-nesting step of tools/deploy_plugin.ps1.
#
# Prereqs (already set up on this machine; see MAC_BUILD_HANDOFF.md):
#   - Xcode Command Line Tools (full Xcode NOT required — Ninja generator)
#   - SDK extracted from "/Applications/Maxon Cinema 4D 2026/sdk.zip" to
#     $C4D_SDK with this module registered in its custom_paths.txt:
#       MODULE <repo>/native/bricklibrary.inline_gui
#   - cmake >= 3.30 + ninja under ~/Dev/tools (no Homebrew needed)
#
# The SDK's cmake/sdk_compiler_helper.cmake needs one local patch for Ninja
# (split the compound "-Xarch_x86_64 -msse4.2" flag); already applied to the
# extract at $C4D_SDK. Re-extracting sdk.zip requires re-applying it.

set -e

C4D_SDK="${BRICK_C4D_SDK:-$HOME/Dev/c4d_sdk_2026}"
TOOLS="$HOME/Dev/tools"
export PATH="$TOOLS:$TOOLS/cmake-3.31.10-macos-universal/CMake.app/Contents/bin:$PATH"

# System frameworks the Maxon static libs reference. The SDK's own
# projectdefinition FRAMEWORKS.OSX plumbing emits compound flags only the
# Xcode generator parses, so pass them as plain linker flags instead.
FW="-framework CoreFoundation -framework Foundation -framework CoreServices \
-framework AppKit -framework CoreGraphics -framework IOKit -framework Security \
-framework SystemConfiguration"

cmake -S "$C4D_SDK" -B "$C4D_SDK/_build_ninja" -G "Ninja Multi-Config" \
  -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_SHARED_LINKER_FLAGS="$FW" -DCMAKE_MODULE_LINKER_FLAGS="$FW"
cmake --build "$C4D_SDK/_build_ninja" --config Release

OUT="$C4D_SDK/_build_ninja/bin/Release/plugins/bricklibrary.inline_gui"
[[ -f "$OUT/bricklibrary.inline_gui.xlib" ]] || { echo "Build output missing: $OUT" >&2; exit 1; }

# Discover the C4D 2026 instance folder (per-machine hash suffix), mirroring
# deploy_plugin.ps1. Override with BRICK_C4D_ROOT.
if [[ -n "$BRICK_C4D_ROOT" && -d "$BRICK_C4D_ROOT" ]]; then
  C4D_ROOT="$BRICK_C4D_ROOT"
else
  C4D_ROOT=$(ls -dt "$HOME/Library/Preferences/Maxon/Maxon Cinema 4D 2026"*/ 2>/dev/null | head -1)
  [[ -n "$C4D_ROOT" ]] || { echo "No C4D 2026 prefs folder found; set BRICK_C4D_ROOT" >&2; exit 1; }
fi

# Nest inside whichever Cubit install folder exists (Cubit-macOS or Cubit).
PLUG=""
for name in Cubit-macOS Cubit; do
  [[ -d "$C4D_ROOT/plugins/$name" ]] && { PLUG="$C4D_ROOT/plugins/$name"; break; }
done
[[ -n "$PLUG" ]] || { echo "No Cubit plugin folder under $C4D_ROOT/plugins" >&2; exit 1; }

rm -rf "$PLUG/bricklibrary.inline_gui"
cp -R "$OUT" "$PLUG/bricklibrary.inline_gui"
echo "Installed: $PLUG/bricklibrary.inline_gui/bricklibrary.inline_gui.xlib"
echo "Restart Cinema 4D to load it."
