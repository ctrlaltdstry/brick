# Cubit Plugin Install

Supported: Cinema 4D 2026 (any 2026.x point release) on Windows and macOS
(Apple Silicon).

The download is one folder with a half per OS:

```text
Cubit <version>/
    MacOS/
        Install Cubit (Mac).command   <- Mac users: double-click this
        Cubit/
    Windows/
        Cubit/                        <- Windows users: copy this into plugins
```

## macOS — easiest install (recommended)

1. Unzip the download.
2. Open the `MacOS` folder and **double-click `Install Cubit (Mac).command`**.
   - The first time, macOS may say it's "from an unidentified developer." If
     so, **right-click** (or Control-click) the file → **Open** → **Open**.
3. A small Terminal window does the rest (copies Cubit into Cinema 4D's
   plugins folder and clears the macOS download flag). When it says "Done,"
   close it.
4. Quit Cinema 4D if it's open, then start it again.
5. Add a `Cubit` or `Cubify` object from the plugin menu.

### Why the installer (and not just drag-and-drop)?

Cubit's native code is not signed with an Apple Developer certificate, so if
you just copy the files in, macOS blocks each of ~137 binaries with a "cannot
verify ... malware" warning. The installer removes the download (quarantine)
flag so the plugin loads normally. If you prefer to install by hand, see the
manual steps below — you'll need to run the unblock command yourself.

## macOS — manual install (if you skip the installer)

1. In Cinema 4D: **Edit → Preferences → Open Preferences Folder…**, which opens
   `~/Library/Preferences/Maxon/Maxon Cinema 4D 2026_<hash>/`.
2. Quit Cinema 4D.
3. Copy the `MacOS/Cubit` folder into `plugins/` there.
4. **Remove the macOS download flag** (required, or you'll get malware
   warnings). Open Terminal and run, pasting the path to the installed folder:

   ```bash
   xattr -dr com.apple.quarantine ~/Library/Preferences/Maxon/Maxon\ Cinema\ 4D\ 2026_*/plugins/Cubit
   ```

5. Start Cinema 4D.

## Windows install

1. In Cinema 4D: **Edit → Preferences → Open Preferences Folder…**, which opens
   `%APPDATA%\Maxon\Maxon Cinema 4D 2026_<hash>\`.
2. Close Cinema 4D.
3. Copy the `Windows\Cubit` folder into `plugins\` there. Final layout:

   ```text
   ...\Maxon Cinema 4D 2026_<hash>\plugins\Cubit\
       c4d_brick_generator.pyp
       brick\
       brickit\
       res\
       vendor\
       bricklibrary.inline_gui\   (native module, .xdl64)
   ```

4. Start Cinema 4D.
5. Add a `Cubit` or `Cubify` object from the plugin menu.

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

Do not rename files inside the `Cubit` folder. Cinema 4D resource names,
plugin IDs, and parameter IDs are intentionally stable so existing scenes can
load correctly.

The bundled third-party dependency license metadata is included under
`Cubit/vendor/*/*.dist-info/`.
