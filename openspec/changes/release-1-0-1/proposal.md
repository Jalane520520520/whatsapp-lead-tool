## Why
Users on a China network stay on 1.0.0: the launcher asks GitHub once (5 s), fails silently, and runs the old version. The same missing proxy means the WhatsApp QR code never shows. Exported Excel files get a random-number name.

## What Changes
- Offline update package `build/make_update_bat.py` -> `更新到X.bat` (zip-wrapped, ~420 KB) that installs a given app version without GitHub or VPN.
- WhatsApp login uses the Windows system proxy (VPN) and shows in the window whether a proxy was found and why login failed (shipped in 1.0.1 code).
- Excel export file name: `<country>_<product>_<date>.xlsx`.

## Capabilities
### New Capabilities
- `update`: getting a user from any installed version to the latest one.
- `whatsapp-login`: QR login through the user's proxy, with visible failure reasons.
- `export`: downloading the result table.

## Out of scope (next change)
- Launcher fallback to a China-reachable host and installer hosted in China: needs a domestic storage account (owner decision); the launcher only changes with a new installer.
- iOS version.

## Impact
`build/make_update_bat.py`, `app/server.py`, `app/window.html`, `wa_check/check.js`.
