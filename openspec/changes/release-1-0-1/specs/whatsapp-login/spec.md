## ADDED Requirements

### Requirement: Login through the system proxy
The system SHALL read the Windows system proxy and use it for WhatsApp login.

#### Scenario: QR with proxy on
- **WHEN** the VPN system proxy is on and the user clicks login
- **THEN** a QR code image appears within 90 s

#### Scenario: No proxy, clear message
- **WHEN** no system proxy is set and WhatsApp is unreachable
- **THEN** the window shows, in Chinese, that no proxy was found and to turn on the VPN system proxy, instead of raw error text
