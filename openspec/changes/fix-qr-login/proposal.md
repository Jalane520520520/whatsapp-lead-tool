# Proposal

## Why

On 1.0.1 with a VPN in mainland China the QR now appears (the system-proxy fix works), but login still fails two ways: in phone-number mode the number box is wiped on every status poll so it cannot be typed into, and after a QR scan the phone says "check your network connection". The phone-number route is the best fallback when QR linking fails, and right now the cause of the scan failure cannot be seen from the window.

## What Changes

- The phone-number input keeps what the user typed (and focus) across status refreshes.
- `login.log` records whether the WhatsApp web version was fetched live or fell back to a default, and the window shows a plain Chinese hint when it fell back (old version = WhatsApp refuses the link).
- The login card shows which proxy the login used, so a support screenshot answers "was the VPN proxy used?".

## Capabilities

### New Capabilities
- `whatsapp-login`: linking the tool to a WhatsApp account by QR or 8-digit code, including diagnostics shown when linking fails.

### Modified Capabilities

## Impact

- `app/window.html` (login card rendering, input state)
- `wa_check/check.js` (login.log lines on version source)
- `app/server.py` (`/status` exposes version source / proxy used)
- Hot-updatable app code only; launcher untouched.
