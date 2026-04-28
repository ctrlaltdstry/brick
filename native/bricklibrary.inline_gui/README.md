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

- `MODULE Z:/02_MKE/2026/BRICK/brick/native/bricklibrary.inline_gui`

Configure and build from the SDK root:

```powershell
cd "C:\Dev\c4d_sdk_2026"
cmake -S . -B build-win64 -G "Visual Studio 17 2022" -A x64
cmake --build build-win64 --config Release
```

Built plugins are emitted under the SDK build output `bin/<config>/plugins`.
