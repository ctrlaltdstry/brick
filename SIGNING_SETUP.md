# macOS code-signing + notarization setup

Goal: sign + notarize Cubit's macOS binaries so users install by plain
drag-and-drop with NO "Apple could not verify ... malware" warnings, and the
`Install Cubit (Mac).command` quarantine-stripping installer is no longer
required.

This is a ONE-TIME setup. After it's done, every signed release is one command:
`python3 tools/package_plugin.py --platform mac --sign --zip`.

- Apple Developer Team ID: **87DC46P9EQ**
- Signing happens on the Mac dev machine (it has `codesign` + `notarytool`).

## State / checklist

- [x] Enrolled in Apple Developer Program (Team ID 87DC46P9EQ)
- [x] CSR generated: `~/Dev/cubit_signing/CubitDeveloperID.certSigningRequest`
      (private key `cubit_devid.key` kept there, chmod 600, never committed)
- [ ] **YOU:** upload CSR → download "Developer ID Application" cert (step 1)
- [ ] Claude: import the cert into the keychain (step 2)
- [ ] **YOU:** create an app-specific password (step 3)
- [ ] Claude: store the notary credential as profile `cubit-notary` (step 4)
- [ ] Claude: sign + notarize a test build, confirm numpy/scipy load (step 5)

## Step 1 — create the certificate (needs your Apple login)

1. Go to <https://developer.apple.com/account/resources/certificates/add>.
2. Under **Software**, choose **Developer ID Application**. Continue.
   (If it's greyed out, you must be signed in as the Account Holder — that's
   you, since it's your account.)
3. Profile Type **G2 Sub-CA** (the default) is fine.
4. Upload `~/Dev/cubit_signing/CubitDeveloperID.certSigningRequest`.
5. Click **Continue**, then **Download**. You get `developerID_application.cer`.
6. Tell Claude where it downloaded (usually `~/Downloads/`).

## Step 2 — import it (Claude does this)

```bash
security import ~/Downloads/developerID_application.cer \
  -k ~/Library/Keychains/login.keychain-db -T /usr/bin/codesign
security find-identity -v -p codesigning   # should now list Developer ID Application
```

## Step 3 — app-specific password (needs your Apple login)

1. Go to <https://appleid.apple.com> → sign in → **Sign-In and Security** →
   **App-Specific Passwords** → **+**.
2. Name it `cubit-notary`. Apple shows a 16-char password like
   `abcd-efgh-ijkl-mnop`.
3. Give that password to Claude (it's revocable any time from this same page,
   and only works for notarization).

## Step 4 — store the notary credential (Claude does this)

```bash
xcrun notarytool store-credentials cubit-notary \
  --apple-id <your-apple-id-email> --team-id 87DC46P9EQ \
  --password <app-specific-password>
```

## Step 5 — sign, notarize, verify (Claude does this)

```bash
python3 tools/package_plugin.py --platform mac --sign --zip
```

Then a real-world check: install the signed build, restart C4D, confirm the
Cubify Attribute Manager works AND that numpy/scipy still load (hardened
runtime can occasionally block a bundled library; if so, the fix is signing
those with a `disable-library-validation` entitlement — handled if it comes up).

## Notes

- Loose plugin files can't have a notarization ticket *stapled* into them, so
  approval is via Gatekeeper's online check on first load. That's silent on any
  Mac with internet. (A fully-offline-proof variant would wrap the release in a
  signed, stapled `.dmg`/`.pkg` — a possible later enhancement.)
- The unsigned installer path stays in the package as a fallback.
