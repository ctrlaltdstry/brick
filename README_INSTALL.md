# Brick Plugin Install

Supported package: Windows + Cinema 4D 2026 (any 2026.x point release —
tested on 2026.0 and 2026.1).

## Install

1. In Cinema 4D, open **Edit → Preferences**, then click **Open Preferences
   Folder...** at the bottom-left of the dialog. This opens your per-instance
   C4D folder (something like
   `%APPDATA%\Maxon\Maxon Cinema 4D 2026_<hash>\`).
2. Close Cinema 4D.
3. In that folder, open `plugins\` and copy the entire `Brick` folder into it.
   The final layout should be:

   ```text
   ...\Maxon Cinema 4D 2026_<hash>\plugins\Brick\
       c4d_brick_generator.pyp
       brick\
       brickit\
       res\
       vendor\
       bricklibrary.inline_gui\   (optional native module)
   ```

4. Start Cinema 4D.
5. Add either object from the plugin menu:
   - `Brick` for a single brick generator.
   - `BrickIt` for a source-mesh-to-brick assembly generator.

## Included Runtime

This package is self-contained for the supported Windows Cinema 4D 2026 build.
It includes:

- The Cinema 4D Python plugin files.
- The core `brick` geometry/fitting package.
- The BrickIt assembly package.
- Cinema 4D resources and icons.
- The native Brick library GUI when available.
- Vendored Windows Python 3.11 builds of `numpy` and `scipy`.

You should not need to install Python packages manually for this supported
package.

## Notes

Do not rename files inside the `Brick` folder. Cinema 4D resource names,
plugin IDs, and parameter IDs are intentionally stable so existing scenes can
load correctly.

The bundled third-party dependency license metadata is included under
`Brick/vendor/*.dist-info/`.
