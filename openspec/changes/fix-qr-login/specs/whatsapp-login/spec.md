# Spec Delta

## Purpose

Link the tool to the user's WhatsApp account by QR code or 8-digit pairing code from a Windows PC behind a VPN, and explain in Chinese why linking failed.

## ADDED Requirements

### Requirement: Phone-number input survives status refresh
The phone-number field in the login card SHALL keep the typed text and keyboard focus while the window refreshes its status.

#### Scenario: Typing a number while the window polls
- **WHEN** the user switches to phone-number login and types `+86 186 0000 0000` slowly over 15 s
- **THEN** the field still shows every character typed and the cursor stays in the field

#### Scenario: Requesting the code
- **WHEN** the user has typed a number and clicks 获取 8 位码
- **THEN** an 8-digit code appears in the card within 90 s with the VPN system proxy on

### Requirement: Login shows why a link may be refused
When the live WhatsApp web version cannot be fetched, the system SHALL record this in `login.log` and show a Chinese hint in the login card.

#### Scenario: Web version fetch fails
- **WHEN** login starts and the web version request through the proxy fails
- **THEN** `login.log` contains a line saying the version fell back to default, and the card shows a Chinese hint that the phone may refuse the scan and to check the VPN or use phone-number login

#### Scenario: Web version fetch succeeds
- **WHEN** login starts on a China network with the VPN system proxy on
- **THEN** `login.log` contains a line with the live version number and no fallback hint is shown

### Requirement: Login card shows the proxy used
The login card SHALL show the proxy address the login used, or 无 when none.

#### Scenario: Proxy visible for support
- **WHEN** the user clicks 显示二维码 with the VPN system proxy on
- **THEN** the card shows the proxy host:port in small text
