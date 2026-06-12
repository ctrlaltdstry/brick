# Windows native build TODO (handoff)

Context for a Claude/Cursor instance running on Mike's **Windows** machine.
One task: build the Windows `bricklibrary.inline_gui` native module and commit
it into the repo, so the cross-platform packager can ship a complete two-OS
package. The macOS side of all this is already done (see `MAC_BUILD_HANDOFF.md`).

## Why

`tools/package_plugin.py` now builds the full distribution
(`dist/Cubit <version>/{MacOS,Windows}/Cubit <version>/`) from either machine,
sourcing the compiled native GUI modules from committed copies under
`native/builds/`. The mac build (`macos_arm64/.../*.xlib`) is committed; the
Windows build (`win64/.../*.xdl64`) is NOT yet. Until it is, packages cut from
the Mac have an empty Cubify Attribute Manager on Windows.

## Steps (all on the Windows machine)

1. Pull this branch (`feature/per-frame-fit-cache`, or wherever these commits
   landed after merge).

2. Build the module exactly as before (SDK already set up at
   `C:\Dev\c4d_sdk_2026` with this module in its `custom_paths.txt`):

   ```powershell
   cd C:\Dev\c4d_sdk_2026
   cmake -S . -B build-win64 -G "Visual Studio 17 2022" -A x64
   cmake --build build-win64 --config Release
   ```

3. Copy the built module into the repo and stamp it:

   ```powershell
   cd C:\Dev\BRICK\brick   # adjust to the repo path on this machine
   Remove-Item -Recurse -Force native\builds\win64\bricklibrary.inline_gui -ErrorAction SilentlyContinue
   New-Item -ItemType Directory -Force native\builds\win64 | Out-Null
   Copy-Item -Recurse C:\Dev\c4d_sdk_2026\build-win64\bin\Release\plugins\bricklibrary.inline_gui native\builds\win64\bricklibrary.inline_gui
   python tools\native_stamp.py write native\builds\win64\bricklibrary.inline_gui
   ```

   (The stamp records a hash of `native/bricklibrary.inline_gui/source` +
   `project` so the packager can detect when the binary goes stale.)

4. Sanity-check, commit, push:

   ```powershell
   python tools\native_stamp.py check native\builds\win64\bricklibrary.inline_gui
   git add native\builds\win64
   git commit -m "win: commit built bricklibrary.inline_gui to native/builds/win64"
   git push
   ```

5. Verify the full package now builds clean (no warnings):

   ```powershell
   python tools\package_plugin.py --zip
   ```

## Notes

- The C++ source gained five `static` qualifiers on `Register*()` functions
  (clang requirement). MSVC accepts them fine; the Windows build needs no
  source changes.
- After this is done, every future release can be cut entirely from the Mac;
  this machine is only needed again if `native/bricklibrary.inline_gui/source`
  changes (the packager's stamp check will say so).
- This file can be deleted once the commit lands.
