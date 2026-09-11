# Week 6

## Monday

### Task Detail

Prepared and submitted weekly progress report for Week 6 to both company supervisor and university. Explored Maestro.dev as a potential automation testing tool — Akram (dev) uses it, investigating whether it can help with testing workflow. Started building Hermes automation for the logbook system. Completed OC Global Tech profile form provided by Hana.

### Issue

Maestro.dev exploration is in early stages — need to evaluate suitability for our testing workflow.

### Proposed Solution

Continue evaluating Maestro.dev features and compare with existing testing tools. Coordinate with Akram on integration approach.

### Status

In Progress

### Total Hours

8 hours

***

## Tuesday

### Task Detail

- **QA / Ocare testing**
  - Worked on the Maestro authentication test case (TC-001).
  - Updated the test flow for: app launch/onboarding, age confirmation checkbox, continue button, email/ID input, password input, login flow.
  - Investigated an issue where Maestro was entering the password into the email field instead of the password field.
  - Discussed using Maestro Studio / hierarchy inspection to identify the correct element selectors.
- **SOS Case Management**
  - Investigated an error occurring when a Coordinator escalates an SOS case.
  - Identified the response as a HTTP 500 Internal Server Error.
  - Determined this should be logged as a Backend/API bug.
  - Prepared a complete bug report including: bug title, priority, module/feature, reproduction steps, actual vs expected result, API endpoint, error response, impact, suspected backend area.
  - Attempted to prepare it for Notion, but the Notion integration wasn't connected.
- **Project / Development**
  - Reviewed and discussed technical issues around the current Ocare testing workflow and API behavior.
  - Continued refining how the QA test cases should document failures and expected results.

### Status

Completed

### Total Hours

8 hours

***

## Wednesday

No notes provided — please share your work for Wednesday.

***

## Thursday

No notes provided — please share your work for Thursday.

***

## Friday

### Task Detail

Completed three major deliverables for the Creator Research System:

1. **Cron job setup and execution** — Created a scheduled cron job running every 3 minutes (5 repeats) with continuity mode. 3 of 5 runs succeeded, discovering and scraping 22 new creators across TikTok, YouTube, Instagram, and Threads. 2 runs failed due to a hermes scheduler "fire claim lost" error.

2. **CRM data quality cleanup** — Cleaned data/Creator-Intel-CRM-List.csv: normalized all platform names to canonical casing, removed 18 invalid rows (12 Facebook post/video URLs + 6 duplicates), fixed 3 Facebook @p handles. CRM went from 1065 → 1047 → 1049 rows (after cleanup and 2 manual scrapes).

3. **AGENTS.md documentation** — Extended AGENTS.md with Sections 17 and 18 documenting mandatory CRM Data Quality & CSV Formatting rules, including schema guardrails, normalization rules, EvidenceJSON formatting, CSV encoding safety, and a 12-step mandatory processing order with hard failure rules.

Also updated .gitignore to exclude obsidian/, deleted temporary Python scripts, and created a pre-cleanup CRM backup.

### Issue

1. **Cron scheduler "fire claim lost" error** — Runs 1 and 2 failed due to hermes scheduler restarts. Remaining 3 runs completed successfully, confirming the task workflow is correct. Appears to be a scheduler stability issue.
2. **Lowercase platform entries after scrapes** — Newly scraped entries had lowercase platform values. Fixed immediately. Consider adding platform normalization to merge_to_crm() to prevent recurrence.
3. **input_channels.csv modified by cron process** — Discovery workflow appended 10 new creators (991 → 1001 rows). Expected behavior per AGENTS.md Section 3.5.

### Proposed Solution

1. **Cron scheduler** — Monitor next cycle for recurrence. If errors persist, investigate scheduler restart behavior or increase delay. No task logic changes needed.
2. **Lowercase platforms** — Add platform normalization to merge_to_crm() in Code/scraper/common.py.
3. **input_channels.csv** — No change needed; modification is expected behavior.

### Status

Completed

### Total Hours

7 hours

***

# Weekly Summary

Week 6 began with reporting for Week 6 to both company and university. Explored Maestro.dev for automation testing (Akram uses it). Started building Hermes automation for the logbook system. Completed OC Global Tech profile form provided by Hana. On Tuesday, focused on Ocare QA automation + bug investigation — Maestro authentication testing (TC-001), the password-field issue, and the SOS escalation API failure (HTTP 500). Prepared a bug report but Notion integration wasn't connected.

# Suggested Attachments

1. Week 6 reporting screenshots
2. Maestro.dev exploration notes
3. OC Global Tech profile form confirmation
4. Maestro TC-001 test flow documentation
5. SOS case escalation bug report