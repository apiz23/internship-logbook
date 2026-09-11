# Week 6

## Monday (Sep 7)

### Task Detail

Prepared and submitted weekly progress report for Week 6 to both company supervisor and university. Explored Maestro.dev as a potential automation testing tool — Akram (dev) uses it, investigating whether it can help with testing workflow. Started building Hermes automation for the logbook system. Completed OC Global Tech profile form provided by Hana. Created this skills creator using Claude skills to build the logbook skills for internship.

### Issue

Maestro.dev exploration is in early stages — need to evaluate suitability for our testing workflow.

### Proposed Solution

Continue evaluating Maestro.dev features and compare with existing testing tools. Coordinate with Akram on integration approach.

### Status

In Progress

### Total Hours

8 hours

***

## Tuesday (Sep 8)

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
  - Refactored the Creator Research System's scraper codebase to support configurable AI model providers, removing a hard dependency on a local Ollama instance so the project can run against a hosted model instead.
  - Added a per-run record limit (`--limit` flag) to all platform scrapers to enable safe small-batch testing.
  - Extracted and documented engineering conventions as `references/scraping-patterns.md`.
  - Separated project-specific configuration (AGENTS.md) from the reusable skill procedure (SKILL.md).
  - Fixed internship-logbook skill command documentation — `/log`, `/review`, `/weekly` documented as slash commands but are actually natural-language trigger phrases.
  - Also corrected the internship-logbook skill's command documentation, which incorrectly described trigger phrases as slash commands.
  - Fixed 13 failing Notion tests (HTTPResponseError being None when httpx unavailable) — test suite now 64/64 passing.

### Issue

1. Maestro.dev exploration is in early stages — need to evaluate suitability for our testing workflow.
2. Notion integration wasn't connected — bug report couldn't be synced.
3. Creator Research System still requires hard dependency on local Ollama instance (being resolved via model_client.py).

### Proposed Solution

1. Continue evaluating Maestro.dev features and compare with existing testing tools. Coordinate with Akram on integration approach.
2. Continue verifying the packaged skill in a clean environment before handing off to the supervisor. Confirm the supervisor's setup (model provider, Hermes skill installation) completes successfully once shared.
3. Continue investigating the difference between working Google Drive authentication test and the sync authentication flow.

### Status

Completed (today's scope) — Creator Research System skill packaging is Completed; supervisor onboarding is Pending.

### Total Hours

8 hours

***

## Wednesday (Sep 9)

### Task Detail

- **Creator Scraper & CRM**
  - Discovered and added 11 new AI content creators to the CRM and Obsidian notes.
  - Scraped 37 TikTok profiles, with 33 unique records successfully synced to the CRM.
  - Audited all 10 platform scrapers and fixed broken `PROJECT_ROOT` paths.
  - Created `common.py` for shared scraper utilities and `run.py` as a unified scraper dispatcher.
  - Added CSV batch processing and automatic platform detection.
  - Added model override support using `--model-provider` and `--model-name`.
  - Improved the Threads scraper with additional extraction strategies, achieving 92.4% follower data completeness.
  - Cleaned 9 Facebook records containing Malay UI text contamination.
  - Created an automated CRM Data Quality Report covering platform and field-level data quality.
- **Ocare QA & Security**
  - Tested Admin/Coordinator RBAC and URL manipulation.
  - Confirmed unauthorized access and update behavior across roles.
  - Classified the finding as a Critical authorization vulnerability.
  - Planned further API, IDOR, session, and permission testing.
- **Internship Logbook & Google Drive**
  - Removed the previous Notion integration.
  - Implemented Local Markdown → Google Drive synchronization for daily, weekly, and project logs.
  - Added duplicate prevention, update detection, and regression tests.
  - Verified 36/36 tests passing and synced 32 existing log files to Google Drive.
  - Continued investigating an authentication/configuration issue affecting the final sync flow.

### Issue

1. Ocare has a critical RBAC authorization issue requiring further security testing.
2. Google Drive authentication works in the test command but still requires verification in the actual sync command.
3. Threads scraping previously had significant missing data, which was improved through additional extraction strategies.

### Proposed Solution

1. Continue API, IDOR, session, and permission testing for the Ocare RBAC issue.
2. Fix the difference between the working Google Drive authentication test and the sync authentication flow.
3. Continue monitoring scraper data quality and Threads extraction accuracy.

### Status

In Progress

### Total Hours

8 hours

***

## Thursday (Sep 10)

### Task Detail

Worked on two internal development activities: refinement of the Internal Issue Management Platform and improvement of the Creator Research System automation.

- **Internal Issue Management Platform**
  - Refined the platform concept as an internal ticketing system connecting QA findings with developer workflows through GitHub.
  - Explored additional future functionality: DevInsight-based developer intelligence, monthly developer contribution scoring, and an optional AI recommendation phase.
  - Clarified that AI recommendations should only recommend suitable developers and must not automatically assign issues.
- **Creator Research System**
  - Conducted web-based discovery of AI content creators across TikTok and Facebook.
  - Verified each candidate's public profile, checked for duplicates against the CRM and input queue using case-insensitive ProfileURL normalization.
  - Executed per-URL scraping via the existing scraper pipeline.
  - Configured and monitored a Hermes scheduled cron job for periodic discovery automation.
  - Cron job discovered 6 new AI content creators: 5 TikTok and 1 Facebook.
  - Inspected `data/output/run_dispatch_output.csv` containing @pebblely_ai scrape record (16.4K followers, English, GenAI, AIGC: yes).
  - Conducted timestamp investigation to determine attribution of discovered profiles to specific cron runs.
  - Verified environment timezone alignment (Asia/Kuala_Lumpur, UTC+8).
  - Confirmed CRM contained 992 lines at time of verification, with 0 remaining duplicate rows after deduplication.

### Issue

1. The creator discovery cron job initially added newly discovered creators to the CRM but did not update `data/input/input_channels.csv`. The issue was identified during verification and subsequently corrected.
2. The repeat: 5 parameter combined with schedule: every 5m has uncertain termination behavior — it is not yet confirmed whether the job will auto-stop after the 5th fire or continue indefinitely.
3. No blocking issue identified with the Internal Issue Management Platform planning.

### Proposed Solution

1. Continue monitoring the automated creator discovery workflow to ensure new creators are consistently synchronized across the CRM and input CSV.
2. Monitor the cron job after the final expected fire (~15:20–15:25 window). If the job remains enabled, manually pause or remove it to prevent unintended recurring executions tomorrow.
3. For the Internal Issue Management Platform, proceed with the core ticketing functionality first and keep AI-powered developer recommendation as an optional final phase.

### Status

Completed (discovery, deduplication, per-URL scraping, verification, and cron job setup/monitoring completed). Cron job repeat-behavior verification and potential manual removal remain pending.

### Total Hours

~8 hours

***

## Friday (Sep 11)

### Task Detail

Completed three major deliverables for the Creator Research System:

1. **Cron job setup and execution** — Created a scheduled cron job running every 3 minutes (5 repeats) with continuity mode enabled. The job executed 5 times; 3 runs successfully discovered and scraped 22 new creators across TikTok, YouTube, Instagram, and Threads, while 2 runs failed due to a hermes scheduler "fire claim lost" error.

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

Week 6 was a heavy week spanning multiple project streams. Monday focused on reporting and Maestro.dev exploration for Ocare testing. Tuesday involved significant Creator Research System refactoring (model_client.py, --limit flags, scraper documentation) plus Ocare QA test case work and SOS bug investigation, with Notion integration issues noted. Wednesday saw major progress on the Creator Research System (37 TikTok profiles scraped, RBAC vulnerability found in Ocare, Google Drive sync implemented for the logbook). Thursday continued with the Internal Issue Management Platform planning and automated creator discovery via Hermes cron job (6 new creators found). Friday was intensive — a full Creator Research System overhaul: cron job pipeline (5 runs, 22 new creators), comprehensive CRM data quality cleanup (1065→1049 rows), and AGENTS.md documentation expansion. Week 6 was marked by steady progress across QA, data research, and automation, with key challenges including Google Drive auth configuration, cron scheduler stability, and Ocare RBAC security findings.

# Suggested Attachments

1. Week 6 reporting screenshots (Monday)
2. Maestro.dev exploration notes (Monday/Tuesday)
3. OC Global Tech profile form confirmation (Monday)
4. Maestro TC-001 test flow documentation (Tuesday)
5. SOS case escalation bug report (Tuesday)
6. Creator Research System skill package (Tuesday)
7. CRM Data Quality Report (Wednesday)
8. Google Drive sync verification results (Wednesday)
9. Internal Issue Management Platform documentation (Thursday)
10. Cron job discovery output and run logs (Thursday/Friday)
11. CRM cleanup backup and report (Friday)
12. AGENTS.md Sections 17-18 documentation (Friday)
