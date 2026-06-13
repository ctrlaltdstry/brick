#!/bin/zsh
# Sign + notarize the macOS Cubit binaries so they install with NO Gatekeeper
# "cannot verify malware" warnings -- i.e. plain drag-and-drop works and the
# quarantine-stripping installer becomes unnecessary.
#
# Prerequisites (one-time, see SIGNING_SETUP.md):
#   1. A "Developer ID Application" certificate for team 87DC46P9EQ in the
#      login keychain (codesign uses it).
#   2. A stored notarytool credential profile named "cubit-notary":
#        xcrun notarytool store-credentials cubit-notary \
#          --apple-id <your-apple-id-email> --team-id 87DC46P9EQ \
#          --password <app-specific-password>
#
# Usage:
#   tools/sign_notarize_mac.sh "dist/Cubit <version>/MacOS/Cubit"
# (Called automatically by package_plugin.py --sign.)

set -e

TEAM_ID="87DC46P9EQ"
NOTARY_PROFILE="cubit-notary"
TARGET="${1:?Usage: sign_notarize_mac.sh <path-to-Cubit-folder>}"

if [[ ! -d "$TARGET" ]]; then
  echo "ERROR: not a folder: $TARGET" >&2; exit 1
fi

# --- 0. Unlock the dedicated signing keychain -------------------------------
# Signing uses a standalone keychain (created during setup) rather than the
# login keychain, so codesign never triggers an interactive password prompt.
# Its password lives in keychain_pw.txt (outside the repo, chmod 600).
SIGN_KC="$HOME/Dev/cubit_signing/cubit-signing.keychain-db"
SIGN_PWFILE="$HOME/Dev/cubit_signing/keychain_pw.txt"
if [[ -f "$SIGN_KC" && -f "$SIGN_PWFILE" ]]; then
  KCPW=$(cat "$SIGN_PWFILE")
  security unlock-keychain -p "$KCPW" "$SIGN_KC" 2>/dev/null || true
  # Make sure codesign keeps non-interactive access to the key after relocks.
  security set-key-partition-list -S apple-tool:,apple:,codesign: \
    -s -k "$KCPW" "$SIGN_KC" >/dev/null 2>&1 || true
fi

# --- 1. Locate the Developer ID Application signing identity -----------------
IDENTITY=$(security find-identity -v -p codesigning 2>/dev/null \
  | grep "Developer ID Application" | grep "$TEAM_ID" | head -1 \
  | sed -E 's/.*\) ([0-9A-F]+) ".*/\1/')

if [[ -z "$IDENTITY" ]]; then
  cat >&2 <<EOF
ERROR: No "Developer ID Application" certificate for team $TEAM_ID found.
Create it first (see SIGNING_SETUP.md). Until then, ship the unsigned package
with the Install Cubit (Mac).command installer.
EOF
  exit 1
fi
echo "Signing identity: $IDENTITY"

# --- 2. Sign every Mach-O, dependencies first -------------------------------
# Hardened runtime (--options runtime) + secure timestamp are required for
# notarization. Sign .dylib, then .so, then the .xlib last so anything that
# links a just-signed lib is signed after it.
sign_one() {
  codesign --force --timestamp --options runtime --sign "$IDENTITY" "$1"
}

echo "Signing dylibs..."
find "$TARGET" -name "*.dylib" -type f -print0 | while IFS= read -r -d '' f; do sign_one "$f"; done
echo "Signing Python extensions (.so)..."
find "$TARGET" -name "*.so" -type f -print0 | while IFS= read -r -d '' f; do sign_one "$f"; done
echo "Signing the native GUI (.xlib)..."
find "$TARGET" -name "*.xlib" -type f -print0 | while IFS= read -r -d '' f; do sign_one "$f"; done

# --- 3. Verify a representative sample --------------------------------------
echo "Verifying signatures..."
XLIB=$(find "$TARGET" -name "*.xlib" -type f | head -1)
[[ -n "$XLIB" ]] && codesign --verify --strict --verbose=1 "$XLIB"

# --- 4. Notarize -------------------------------------------------------------
# notarytool wants a zip of the signed payload. Apple records each signed
# binary's identity, so Gatekeeper approves them on the user's Mac (online
# check) even though loose plugin files can't have a ticket stapled into them.
ZIP="${TARGET:h}/cubit_notarize_payload.zip"
echo "Zipping signed payload for notarization..."
/usr/bin/ditto -c -k --keepParent "$TARGET" "$ZIP"

echo "Submitting to Apple notary service (this can take a few minutes)..."
NOTARY_KC_ARGS=()
[[ -f "$SIGN_KC" ]] && NOTARY_KC_ARGS=(--keychain "$SIGN_KC")
xcrun notarytool submit "$ZIP" --keychain-profile "$NOTARY_PROFILE" "${NOTARY_KC_ARGS[@]}" --wait

rm -f "$ZIP"
echo
echo "Done. The signed Cubit folder at:"
echo "  $TARGET"
echo "is notarized. Re-zip the distribution (package_plugin.py does this) and"
echo "users can drag-and-drop install with no Gatekeeper warnings."
