#!/bin/zsh
# Cubit for Cinema 4D — macOS installer.
#
# What this does (and why you need it): macOS tags everything you download
# through a browser with a "quarantine" flag. Cubit ships unsigned native
# code (the brick GUI module + numpy/scipy), so Cinema 4D would otherwise pop
# a "cannot verify ... malware" warning for each of ~137 files. This script
# copies Cubit into Cinema 4D's plugins folder and removes that flag so the
# plugin just works.
#
# HOW TO RUN: double-click this file. The first time, macOS may say it
# "cannot be opened because it is from an unidentified developer" — if so,
# right-click (or Control-click) the file, choose Open, then Open again.

set -e

# Resolve the folder this script lives in (the unzipped "MacOS" folder), so
# the Cubit source sits right next to it.
HERE="${0:A:h}"
SRC="$HERE/Cubit"

echo "==============================================="
echo " Cubit for Cinema 4D — macOS installer"
echo "==============================================="
echo

if [[ ! -d "$SRC" ]]; then
  echo "ERROR: couldn't find a 'Cubit' folder next to this installer."
  echo "Make sure you unzipped the download and kept this file beside the"
  echo "Cubit folder, then run it again."
  echo
  read "?Press Return to close."
  exit 1
fi

# Find the Cinema 4D 2026 plugins folder (each install has a unique hash
# suffix). Newest wins if there are several.
MAXON="$HOME/Library/Preferences/Maxon"
C4D_DIR=$(ls -dt "$MAXON/Maxon Cinema 4D 2026"*/ 2>/dev/null | head -1)

if [[ -z "$C4D_DIR" ]]; then
  echo "ERROR: couldn't find a Cinema 4D 2026 folder under:"
  echo "  $MAXON"
  echo "Open Cinema 4D once (Edit > Preferences > Open Preferences Folder)"
  echo "so the folder exists, then run this installer again."
  echo
  read "?Press Return to close."
  exit 1
fi

PLUGINS="${C4D_DIR%/}/plugins"
mkdir -p "$PLUGINS"
DEST="$PLUGINS/Cubit"

echo "Installing to:"
echo "  $DEST"
echo

# Back up any existing install rather than deleting it outright.
if [[ -d "$DEST" ]]; then
  STAMP=$(date +%Y%m%d_%H%M%S)
  echo "Existing Cubit found — moving it to Cubit.backup_$STAMP"
  mv "$DEST" "$PLUGINS/Cubit.backup_$STAMP"
fi

echo "Copying files..."
cp -R "$SRC" "$DEST"

echo "Removing the macOS download (quarantine) flag..."
xattr -dr com.apple.quarantine "$DEST" 2>/dev/null || true

echo
echo "==============================================="
echo " Done. Cubit is installed."
echo
echo " Next: fully quit Cinema 4D if it's open, then"
echo " start it again. Add a Cubit or Cubify object —"
echo " no security warnings this time."
echo "==============================================="
echo
read "?Press Return to close."
