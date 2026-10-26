## 1. Update
- [x] 1.1 `build/make_update_bat.py` builds the offline update .bat + zip. Spec: update/Update with dead proxy. Proof: Wuying run, `out_upgrade.txt` (exit 0, footer 1.0.1).
- [x] 1.2 Failure path prints `更新没成功` + reason. Spec: update/Update fails visibly. Proof: Wuying run with install folder renamed.
- [x] 1.3 Online update regression. Spec: update/Online update. Proof: Wuying clean 1.0.0 log line.

## 2. WhatsApp login
- [x] 2.1 System proxy used for login (1.0.1 code). Spec: whatsapp-login/QR with proxy on. Proof: GitHub Windows runner run 40052490589 showed QR. China network: NOT VERIFIED (Wuying has no overseas exit) - confirmed only by the user.
- [ ] 2.2 No-proxy message in Chinese. Spec: whatsapp-login/No proxy, clear message. Proof: Wuying, proxy off, screenshot of window text.

## 3. Export
- [ ] 3.1 Export file name `X_Y_date.xlsx`. Spec: export/Download Excel. Proof: Wuying, click download, list Downloads folder, open file row count = table row count.

## 4. Finish
- [ ] 4.1 Run every scenario above on Wuying once more, build zip, write the user message, owner says send.
- [ ] 4.2 `openspec archive release-1-0-1` after the user confirms 1.0.1 on their machine.
