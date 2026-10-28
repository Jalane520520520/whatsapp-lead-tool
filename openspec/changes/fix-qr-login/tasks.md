# Tasks

## 1. Phone-number input

- [x] 1.1 Keep the phone field value, focus and caret across re-renders — `app/window.html`; satisfies "Typing a number while the window polls"; prove: open the window locally (`python launcher.py`), switch to phone mode, type for 15 s, field keeps text; then repeat on Wuying. — Mac: old file field empty after 15 s typing, new file keeps value+focus. Wuying: NOT VERIFIED (no Wuying session)
- [ ] 1.2 Check code request end to end — no file change; satisfies "Requesting the code"; prove: on Wuying with VPN system proxy on, type number, click 获取 8 位码, code shows within 90 s.

## 2. Version-source diagnostics

- [x] 2.1 Log `source=live|fallback|default` in the `connect` line — `wa_check/check.js`; satisfies both "Web version" scenarios; prove: `node wa_check/check.js --login-only` with `WAT_PROXY=127.0.0.1:1` (dead proxy) logs `source=default`/`fallback`, with a working proxy logs `source=live`. — dead proxy -> source=fallback (older version 1043857760), direct -> source=live (1051977695). Wuying: NOT VERIFIED
- [x] 2.2 Expose the source in `/status` and show the Chinese hint when not live — `app/server.py`, `app/window.html`; satisfies "Web version fetch fails"; prove: `curl localhost:<port>/status` shows the field; card shows the hint with the dead proxy. — /status wa_source=fallback; hint shown for fallback, hidden for live. Wuying: NOT VERIFIED

## 3. Proxy shown

- [x] 3.1 Render proxy host:port (or 无) in small text in the login card — `app/window.html`; satisfies "Proxy visible for support"; prove: screenshot on Wuying with VPN on. — Mac: card shows 代理：无. Wuying screenshot: NOT VERIFIED

## 4. Release

- [ ] 4.1 Bump `VERSION`, build update zip with `build/make_update_bat.py`; prove: update applied on Wuying shows new version bottom-right.
