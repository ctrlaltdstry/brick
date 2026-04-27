# Brick Library Inline GUI (Native SDK Scaffold)

This module is the C++ SDK starting point for a true inline AM custom GUI
thumbnail library for Brickify.

## Current status

- Buildable command plugin scaffold
- Opens a dockable WIP panel from C++ SDK module
- Next step is implementing a custom AM GUI control and wiring it to
  BrickifyAssembly parameters

## Build integration

This module is referenced from your Cinema 4D SDK `custom_paths.txt` as:

- `MODULE Z:/02_MKE/2026/BRICK/brickify/native/bricklibrary.inline_gui`

Configure and build from the SDK root:

```powershell
cd "C:\Dev\c4d_sdk_2026"
cmake -S . -B build-win64 -G "Visual Studio 17 2022" -A x64
cmake --build build-win64 --config Release
```

Built plugins are emitted under the SDK build output `bin/<config>/plugins`.
