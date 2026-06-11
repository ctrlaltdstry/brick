# Brick Library Inline GUI

This module provides the native custom GUI controls used by the Brick
Attribute Manager UI in Cinema 4D.

## Current status

- Buildable C++ SDK module for inline AM custom GUIs.
- Brick library thumbnail control is active in the `BrickIt` object UI.
- Grid uses square cells, top-left justification, and brick-only entries.
- Hero banner GUI is supported from the same native module.
- Control state is written/read through `BRICKIFYASSEMBLY_LIBRARY_MASK`.

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

This step requires a **Mac** with Xcode + Command Line Tools and the **macOS**
Cinema 4D 2026 C++ SDK (the Windows SDK cannot cross-compile a Mac plugin).

1. Get the macOS C4D 2026 SDK on the Mac and point its `custom_paths.txt` at
   this module (adjust the path to where the repo is cloned on the Mac):

   ```
   MODULE /Users/you/Dev/BRICK/brick/native/bricklibrary.inline_gui
   ```

2. Configure + build with the SDK's bundled macOS preset (Xcode generator):

   ```bash
   cd /path/to/c4d_sdk_2026
   cmake --preset macos_universal_xcode      # generates the Xcode project
   cmake --build --preset macos_universal_xcode --config Release
   # (or open the generated .xcodeproj and build the bricklibrary.inline_gui
   #  target in Release)
   ```

3. The built module lands under the SDK build output, e.g.
   `build/.../bin/Release/plugins/bricklibrary.inline_gui` (a macOS plugin
   bundle, not a Windows .xdl64). Copy that whole `bricklibrary.inline_gui`
   folder into the Mac plugin package next to `c4d_brick_generator.pyp`
   (the same nested location the Windows deploy uses).

4. Re-zip the Mac package and reinstall. The Cubify Attribute Manager should
   now populate, identical to Windows.

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
