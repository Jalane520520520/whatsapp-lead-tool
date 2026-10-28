# Design

## Context

The window re-renders the whole login card from a template string on every `/status` poll (`app/window.html`, `loginCard()`), so the `<input id=ph>` is recreated empty. `check.js` already fetches the web version through the proxy (`webVersion()`) and silently falls back to `fetchLatestBaileysVersion()` or the library default; `login.log` logs the final version but not its source.

## Goals / Non-Goals

**Goals:** typing in the phone field works; the fallback-version case is visible on screen and in the log; the proxy used is visible.

**Non-Goals:** changing the proxy transport, adding SOCKS/TUN support, fixing the phone-side VPN.

## Decisions

- **Keep input state in a JS variable, restore after render** (value + focus + caret) rather than skipping re-render while typing. Smallest change; alternative (diffing DOM / only updating the QR box) touches more of the page.
- **Log `version source=live|fallback|default`** in the existing `connect` log line; `/status` reads the last `connect` line from `login.log`. Avoids a new file; alternative (a JSON status file) is cleaner but more code.
- **Proxy shown from `/status.proxy`**, which already exists; only rendering changes.

## Risks / Trade-offs

- [Phone-side "check network" may be the phone's VPN, not ours] → the hint names both causes and suggests phone-number login.
- [Parsing log text is brittle] → match a fixed `source=` token written by our own code.
