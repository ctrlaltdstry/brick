# Cubit Plugin Install

Supported: Cinema 4D 2026 (any 2026.x point release) on Windows and macOS
(Apple Silicon).

The package is one folder with a half per OS:

```text
Cubit <version>/
    MacOS/
        Cubit <version>/     <- install this folder on a Mac
    Windows/
        Cubit <version>/     <- install this folder on Windows
```

## Install

1. In Cinema 4D, open **Edit → Preferences**, then click **Open Preferences
   Folder...** at the bottom-left of the dialog. This opens your per-instance
   C4D folder:
   - Windows: `%APPDATA%\Maxon\Maxon Cinema 4D 2026_<hash>\`
   - macOS: `~/Library/Preferences/Maxon/Maxon Cinema 4D 2026_<hash>/`
2. Close Cinema 4D.
3. In that folder, open `plugins/` and copy the `Cubit <version>` folder for
   **your OS** (from `MacOS/` or `Windows/`) into it. The final layout:

   ```text
   .../Maxon Cinema 4D 2026_<hash>/plugins/Cubit <version>/
       c4d_brick_generator.pyp
       brick/
       brickit/
       res/
       vendor/
       bricklibrary.inline_gui/   (native module: .xdl64 on Windows, .xlib on Mac)
   ```

4. Start Cinema 4D.
5. Add either object from the plugin menu:
   - `Cubit` for a single brick generator.
   - `Cubify` for a source-mesh-to-brick assembly generator.

## Included Runtime

Each OS half is self-contained for its platform. It includes:

- The Cinema 4D Python plugin files.
- The core geometry/fitting package.
- The mesh-to-assembly (Cubify) package.
- Cinema 4D resources and icons.
- The native brick-library GUI for that OS (required — without it the Cubify
  Attribute Manager shows no parameters).
- Vendored Python 3.11 builds of `numpy` and `scipy` for that OS.

You should not need to install Python packages manually.

## Notes

Do not rename files inside the `Cubit <version>` folder. Cinema 4D resource
names, plugin IDs, and parameter IDs are intentionally stable so existing
scenes can load correctly.

The bundled third-party dependency license metadata is included under
`Cubit <version>/vendor/*/*.dist-info/`.
