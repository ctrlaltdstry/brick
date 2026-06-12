# Brick Library Inline GUI

This module provides the native custom GUI controls used by the Brick
Attribute Manager UI in Cinema 4D.

## Current status

- Buildable C++ SDK module for inline AM custom GUIs.
- Brick library thumbnail control is active in the `BrickIt` object UI.
- Grid uses square cells, top-left justification, and brick-only entries.
- Hero banner GUI is supported from the same native module.
- Control state is written/read through `BRICKIFYASSEMBLY_LIBRARY_MASK`.

## Keeping platform builds in sync (read this before packaging)

The compiled binaries are **committed to the repo** under `native/builds/`:

- `native/builds/macos_arm64/bricklibrary.inline_gui/` (.xlib)
- `native/builds/win64/bricklibrary.inline_gui/` (.xdl64)

so either machine can run `python3 tools/package_plugin.py` and get the full
two-OS distribution. Each build folder carries a `build_info.txt` stamp — a
hash of this module's `source/` + `project/` written by
`tools/native_stamp.py`. The packager checks the stamp and **warns if the C++
source changed after the binary was built** (= rebuild needed on that OS).

Workflow when you touch the C++ source:

1. Rebuild on each OS:
   - Mac: `tools/build_native_mac.sh` (auto-refreshes `native/builds/macos_arm64`
     and its stamp).
   - Windows: run the cmake build below, then copy the built
     `bricklibrary.inline_gui` folder to `native/builds/win64/` and run
     `python tools/native_stamp.py write native/builds/win64/bricklibrary.inline_gui`.
2. Commit the refreshed `native/builds/` folders along with the source change.

Everything else in the package (Python code, vendored numpy/scipy via
`tools/vendor_deps.py`) is platform-portable and can be produced on any
machine.

## Build integration

This module is referenced from your Cinema 4D SDK `custom_paths.txt` as:

- `MODULE C:/dev/BRICK/brick/native/bricklibrary.inline_gui`

Configure and build from the SDK root:

```powershell
cd "C:\Dev\c4d_sdk_2026"
cmake -S . -B build-win64 -G "Visual Studio 17 2022" -A x64
cmake --build build-win64 --config Release
```

Built plugins are emitted under the SDK build output `bin/<config>/plugins`.

## macOS build (required for the Mac plugin's Attribute Manager)

The Cubify object's `.res` references two custom GUIs implemented here
(`CUSTOMGUIBRICKSOURCES`, `CUSTOMGUIBRICKLIBRARY`). Without this native module,
Cinema 4D on macOS **silently drops the entire object description -> the
Attribute Manager shows no parameters** (geometry still generates, because that
is pure Python). So the Mac plugin bundle MUST include a macOS build of this
module. `source/main.cpp` is platform-agnostic C4D SDK code (no Windows-only
APIs), and `projectdefinition.txt` already declares `Platform=Win64;OSX;Linux`,
so it compiles on macOS without source changes.

This step requires a **Mac** (the Windows SDK cannot cross-compile a Mac
plugin), but — verified 2026-06-11 — neither full Xcode nor a portal download:

- The macOS C++ SDK ships **inside the app**:
  `/Applications/Maxon Cinema 4D 2026/sdk.zip` (matches the installed build
  exactly). Extract to `~/Dev/c4d_sdk_2026`.
- Command Line Tools + portable cmake/ninja are enough; the Ninja generator
  replaces the Xcode-requiring `macos_universal_xcode` preset.

The whole flow (configure, build, install into the user plugin folder) is
scripted: `tools/build_native_mac.sh`. What it encodes, for reference:

1. Point the SDK's `custom_paths.txt` at this module:

   ```
   MODULE /Users/you/Dev/BRICK/brick/native/bricklibrary.inline_gui
   ```

2. One-line patch to the SDK extract's `cmake/sdk_compiler_helper.cmake`
   (Ninja branch passes `"-Xarch_x86_64 -msse4.2"` as a single arg; split it
   — see MAC_BUILD_HANDOFF.md). Re-apply after re-extracting sdk.zip.

3. Configure with Ninja Multi-Config, passing the macOS system frameworks as
   linker flags (the SDK's own framework plumbing is Xcode-generator-only),
   then build Release. Output: `bricklibrary.inline_gui.xlib` — arm64
   Mach-O bundle, ad-hoc linker-signed (fine locally; distribution to other
   Macs may want Developer ID + notarization).

4. Copy the whole `bricklibrary.inline_gui` folder into the Mac plugin
   package next to `c4d_brick_generator.pyp` (the same nested location the
   Windows deploy uses). Restart C4D; the Cubify Attribute Manager should
   populate, identical to Windows.

Note: `tools/package_plugin.ps1 -Platform mac` currently EXCLUDES the native
GUI (it only had a Windows build). Once a macOS build exists, set
`$env:BRICK_NATIVE_GUI_MAC_SOURCE` to its path (or drop it into the package
manually) so the Mac zip includes it.

For user deployment, `tools/deploy_plugin.ps1` nests the built
`bricklibrary.inline_gui` plugin inside the main `Brick` plugin folder so the
Cinema 4D user plugins root contains a single Brick entry. The deploy script
looks for the built module at:

- `$env:BRICK_NATIVE_GUI_SOURCE`
- `C:/Dev/c4d_sdk_2026/build-win64/bin/Release/plugins/bricklibrary.inline_gui`
- the currently installed root-level `plugins/bricklibrary.inline_gui`
