# Brick Plugin Install

Supported package: Windows + Cinema 4D 2026.

## Install

1. Close Cinema 4D.
2. Copy the entire `Brick` folder into your Cinema 4D user plugins folder:

   ```text
   %APPDATA%\Maxon\Maxon Cinema 4D 2026_1ABCDC12\plugins\Brick
   ```

3. Start Cinema 4D.
4. Add either object from the plugin menu:
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
