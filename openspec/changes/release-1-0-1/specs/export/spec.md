## ADDED Requirements

### Requirement: Readable export file name
The system SHALL name the downloaded Excel after the run.

#### Scenario: Download Excel
- **WHEN** the user clicks download after a run for country X and product Y
- **THEN** the saved file is named `X_Y_<YYYY-MM-DD>.xlsx` and opens in Excel/WPS with the same rows as the window table
