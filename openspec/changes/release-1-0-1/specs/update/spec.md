## ADDED Requirements

### Requirement: Offline update without GitHub
The system SHALL provide a single double-click update file that moves an installed 1.0.0 to 1.0.1 with no access to GitHub.

#### Scenario: Update with dead proxy
- **WHEN** a 1.0.0 install runs with HTTPS_PROXY pointing to a dead port and the user double-clicks `更新到1.0.1.bat`
- **THEN** the console prints `更新完成：已更新到 1.0.1`, exit code is 0, and after reopening `launcher.log` ends with `running 1.0.1` and the window footer shows `1.0.1`

#### Scenario: Update fails visibly
- **WHEN** the install folder is missing
- **THEN** the console prints `更新没成功` with the reason and exit code is non-zero

### Requirement: Normal online update still works
The system SHALL keep updating from GitHub releases when GitHub is reachable.

#### Scenario: Online update
- **WHEN** a clean 1.0.0 starts with GitHub reachable
- **THEN** `launcher.log` contains `update: 1.0.0 -> 1.0.1` and the window footer shows `1.0.1`
