---
name: internship-logbook
description: Turn short, informal daily notes into a structured, university-style internship/industrial-training logbook, generate weekly reports from them, and generate validated copy-ready university SUBMISSION fields (daily task details, weekly summary, one attachment recommendation) under a hard 4,000-character limit. Use for internship/training/practicum/OJT logbook work, daily logs, weekly/monthly reports, and university portal submissions. Triggers on /log, /review, /weekly, /monthly, /university, /submission, /submit-week, /submit-day, /validate-submission, and on phrases like "generate my university submission", "prepare week N for university submission", "give me Monday to Friday task details", "weekly summary under 4000 characters", "everything I need to copy into the university system", or rough end-of-day notes that should become a logbook entry.
version: 1.1.0
author: Hermes Community
license: MIT
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [productivity, logbook, internship, weekly-report]
    related_skills: []
    config:
      - key: internship.start_date
        description: "Internship start date (YYYY-MM-DD, first official working day)"
        default: ""
        prompt: "Enter your internship start date (YYYY-MM-DD)"
      - key: internship.working_days
        description: "Which weekdays count as working days"
        default: "mon-fri"
        prompt: "Enter working days (e.g., mon-fri, mon-sat)"
      - key: internship.hours_per_day
        description: "Default hours per working day"
        default: "8"
        prompt: "Enter default hours per working day"
      - key: internship.daily_template
        description: "Daily entry template style"
        default: "simple"
        prompt: "Choose daily template style (simple or detailed)"
      - key: internship.weekly_report_timing
        description: "When to generate weekly reports"
        default: "manual"
        prompt: "Weekly report timing (manual on request, or automatic every Friday)"
      - key: submission.enabled
        description: "Enable the university submission generator"
        default: "true"
        prompt: "Enable university submission generation? (true/false)"
      - key: submission.daily_task_char_limit
        description: "Maximum characters per daily task detail field"
        default: "4000"
        prompt: "Daily task detail character limit"
      - key: submission.weekly_summary_char_limit
        description: "Maximum characters for the weekly summary field"
        default: "4000"
        prompt: "Weekly summary character limit"
      - key: submission.working_days
        description: "Working days submitted to the portal"
        default: "mon-fri"
        prompt: "Which weekdays do you submit to the university? (e.g. mon-fri)"
      - key: submission.max_weekly_attachments
        description: "Attachments allowed per weekly submission"
        default: "1"
        prompt: "How many attachments does your portal allow per week?"
required_environment_variables:
  - name: STORAGE_PROVIDER
    prompt: "Storage provider (local or google_drive)"
    help: "Set to 'google_drive' to use Google Drive, or 'local' for local Markdown files"
    required_for: "Choosing Google Drive as storage backend"
  - name: GOOGLE_DRIVE_ROOT_FOLDER_ID
    prompt: "Google Drive root folder ID"
    help: "The Google Drive folder ID where logbook files will be stored"
    required_for: "Google Drive storage functionality"
required_credential_files:
  - path: google_client_secret.json
    description: "Google OAuth2 client secret (created by Google Cloud Console)"
  - path: google_token.json
    description: "Google OAuth2 access token (created by running google_drive_auth.py)"
---

# Internship Logbook

Converts informal daily notes into professional logbook entries and weekly
reports, for anyone doing an internship, industrial training, or practicum
that requires a written logbook. The skill is generic — all personal and
project-specific details live in two places the user fills in themselves:

- `AGENTS.md` — stable facts: who the user is, their internship timeline,
  and their real project details. Read every session.
- `projects/*.md` — optional, for splitting project context out of
  `AGENTS.md` once it gets long

This `SKILL.md` is the procedure — it stays generic and loads only when
doing logbook work. Never hardcode a specific person's name, university,
or project names into it. If the user asks to "add support for" a new
project or detail, that goes into their `AGENTS.md` or `projects/`
folder, not here.

## When to Use

Load this skill whenever the user mentions any of the following:

- "internship logbook", "training logbook", "practicum logbook", "OJT logbook"
- "daily log", "log today's work", "add today's task"
- "weekly report", "generate this week's report", "do the weekly"
- "university submission", "submit to the university", "task details for
  Monday to Friday", "weekly summary under 4000 characters", "validate my
  submission", "prepare week N for university submission"
- Review commands: "review today's entry", "check today's log"
- Rough end-of-day notes like "today I worked on X, tested Y, bug in Z"
  (even without saying "logbook" explicitly)

## Quick Reference

| Action | Trigger phrase | Output |
|--------|---------------|--------|
| Log today's work | "log today's work", "add today's task", "today I worked on..." | Creates/updates `daily/YYYY-MM-DD.md` |
| Review today's entry | "review today's entry", "check today's log" | Checks accuracy, wording, consistency |
| Weekly report | "generate this week's report", "do the weekly" | Creates/updates `weeks/week-XX.md` |
| University submission | "/university", "/submission", "/submit-week", "generate my university submission for this week", "Prepare Week 5 for university submission" | Copy-ready daily task details + weekly summary + one attachment, all measured |
| One submission day | "/submit-day" plus a date | Regenerates a single day's task detail field |
| Submission validation | "/validate-submission", "check my submission" | Dates, hours, limits, missing records, attachment readiness |
| Character count | "is this under 4000 characters?" | Exact count, remaining, over-by, and shortening |

## Procedure

### First-time setup

If the repo doesn't yet have an `AGENTS.md` at its root, walk the user
through creating one from `assets/AGENTS-template.md` before doing
anything else. `AGENTS.md` holds stable facts and expectations (read
every session); this `SKILL.md` holds the procedure (loaded when doing
logbook work) — keep the two separate rather than merging one into the
other. Ask for:

1. Name and role (e.g. "Software Engineering Intern")
2. Institution / program name
3. Internship start date and which weekdays count as working days
   (default: Mon–Fri)
4. Default hours per working day (default: 8)
5. Which daily template style they want — `simple` or `detailed` (see
   `assets/daily-template-simple.md` and `assets/daily-template-detailed.md`)
6. Whether they already have a repo structure (daily/, weeks/, projects/,
   attachments/) or want you to create one — use the layout below if not.

Save their answers into `AGENTS.md`. Don't ask again once it exists —
read it at the start of every session that touches this skill.

If the repo has no `projects/` files yet, that's fine — create the first
one the first time the user mentions a project by name (see "Project
files" below).

### Repository layout

```text
<repo>/
├── AGENTS.md              ← user identity + timeline (read every session)
├── daily/
│   └── YYYY-MM-DD.md       ← one canonical file per calendar date
├── weeks/
│   └── week-XX.md          ← one file per internship week
├── projects/
│   └── <project-name>.md   ← persistent context per project/workstream
├── attachments/
│   └── week-XX/
├── config/
│   └── university-submission.json ← portal profile (local, git-ignored)
└── scripts/
    ├── config.py              ← storage configuration (local + Google Drive)
    ├── google_drive_auth.py   ← OAuth2 authentication for Google Drive
    ├── google_drive_provider.py ← Google Drive storage provider
    ├── university_profile.py  ← submission limits, working days, holidays
    ├── logbook_reader.py      ← read-only parser for daily/ and weeks/
    ├── submission_generator.py ← submission fields + validation
    ├── char_limit.py          ← character counting and shortening
    └── submission_cli.py      ← CLI for the submission commands
```

If the user already has a different layout, adapt to it rather than
forcing this one — the layout matters less than the rules below.

### Storage providers

The logbook supports two storage backends, configured via `scripts/config.py`:

| Provider | Description | Configuration |
|----------|-------------|---------------|
| `local` | Markdown files in the repo (default) | No setup needed |
| `google_drive` | Markdown files in Google Drive | OAuth setup required |

**Local storage (default):** Files are stored directly in the repository as Markdown. No authentication required.

**Google Drive storage:** Requires OAuth2 setup. See the README for setup instructions. The skill declares `required_credential_files` for `google_client_secret.json` and `google_token.json` (stored at `~/.hermes/`), plus `required_environment_variables` for `STORAGE_PROVIDER` and `GOOGLE_DRIVE_ROOT_FOLDER_ID`.

### Core workflow

1. User provides raw daily notes (any format — full sentences, bullet
   fragments, one-liners; never make them reformat first).
2. Determine the correct date (see "Determining the date").
3. Determine the internship week from `AGENTS.md`'s start date (see
   "Date-to-week calculation").
4. Read the relevant `projects/*.md` file(s) for continuity — don't
   generate a description of project work from scratch each time; build
   on what's already recorded there.
5. Create or update `daily/YYYY-MM-DD.md` (see "One date, one file").
6. Update the touched `projects/*.md` file(s) with anything worth
   remembering next time (current status, open issues, PR state).
7. On request (or Friday, if the user has set up that convention),
   generate the week's report.

### Determining the date

- Default to **today's actual date** for phrases like "add today's task",
  "log today", "today I worked on...".
- Only use a different date when the user is explicit about it: "add
  this for Friday", "log this for 2026-09-04", "I forgot to log
  yesterday". Recalculate the week from whatever date is actually used.
- Never infer the date from a previous message or assume a new
  conversation means a new day — always resolve it fresh from what the
  user says plus the real calendar date.

### Date-to-week calculation

`AGENTS.md` stores an internship **start date** and **working days**
(default Mon–Fri). Compute the week number from that:

```
week_number = floor((date - start_date) / 7 days) + 1
```

Week boundaries follow the working-day pattern from the start date, not
calendar Mondays — if the user's internship starts on a Wednesday,
Week 1 runs from that Wednesday through the following Tuesday (or
whatever their working-day set implies). Show your work when it's not
obvious, e.g. "That's Week 6 (started 3 Aug, so 7 Sep falls in the
6th 7-day block)." If `AGENTS.md` has no start date yet, ask for it once
and save it — don't guess.

### One date, one file

There is exactly one canonical daily file per calendar date:
`daily/YYYY-MM-DD.md`.

- **File doesn't exist** → create it from the user's chosen daily
  template (`assets/daily-template-simple.md` or
  `-detailed.md`), filled with the new information.
- **File already exists** → open it, keep everything already there, and
  merge the new information into the right sections. Never overwrite or
  silently drop earlier content, and don't duplicate a fact that's
  already recorded (e.g. if "tested login flow" is already listed,
  don't add it again just because the user mentioned it again).
- Raw notes are the source of truth: preserve every raw note the user
  has given for that day, appending new ones rather than replacing old
  ones.

### Project files

Each ongoing project/workstream gets `projects/<name>.md`. Use it to
track, across the whole internship:

- What the project is and common types of tasks on it
- Current status of anything ongoing (e.g. a PR, a feature, a bug)
- Known issues/areas already documented, so you don't re-describe the
  same finding as if it were new
- Any wording constraints specific to that project (e.g. "never say the
  PR is merged unless the user confirms it")

Update this file whenever a daily entry touches that project — this is
what lets weekly progress read as a real progression ("Week 2: created
initial test cases. Week 3: added more and ran functional testing.")
instead of the same sentence repeated five times.

If a project doesn't have a file yet, create one the first time the
user mentions it, using whatever they've told you so far as the seed
content.

### Accuracy is non-negotiable

This is the most important rule in the whole skill. A logbook is a
factual record that a university or employer will read — inventing
content, even to make an entry sound more complete, undermines the
whole document and can cause real problems for the user.

- Never invent work the user didn't describe: no new features, bugs,
  meetings, deployments, merged PRs, or completed tasks that weren't
  mentioned or previously confirmed.
- Only describe a task as "Completed" if the notes say so. If the notes
  say it's ongoing or waiting on something, use "In Progress", "Pending
  Review", "Pending Merge", or "Blocked" instead.
- Only include an "Issue" when one is stated or clearly implied by the
  notes. If there genuinely isn't one, say so plainly ("No blocking
  issue identified during this task") rather than inventing one to fill
  the section.
- If a generated description contains a claim the raw notes and project
  file don't support, cut it or soften it rather than leave it in.
- When in doubt about what actually happened, ask — don't fill the gap
  with a plausible-sounding guess.

### Turning notes into professional wording

Vague notes can be rephrased more professionally, but the substance must
stay the same. Elevate the phrasing, not the scope of the work.

**Example**
- Raw: `checked login filter, seemed fine`
- Good: `Conducted functional testing of the login filtering feature to confirm it behaved as expected.`
- Too far: `Redesigned and optimized the login filtering architecture.`

See `references/writing-style.md` for the full tone guide (what reads as
a competent intern's own writing vs. an AI-generated corporate report).

### Weekly reports

Before generating `weeks/week-XX.md`:

1. Work out the week's date range from `AGENTS.md`.
2. Check which of the expected daily files exist for that range.
3. If any are missing, tell the user which dates are missing and ask for
   the notes — never fabricate a missing day just to complete the week.
4. Build the report only from verified daily files that actually fall
   inside that week's date range (a Week 5 file must never absorb a
   Week 6 entry or vice versa).

Weekly report shape (adapt headers to the user's chosen working days):

```markdown
# Week XX

## <Day 1>
### Task Detail
### Issue
### Proposed Solution
### Status
### Total Hours

---
[repeat per working day]
---

# Weekly Summary
[projects touched, overall progress, notable issues/limitations, skills
gained — concise, not written like a marketing report]

# Suggested Attachments
1. ...
```

### Suggested attachments and sensitive info

When suggesting evidence for a daily or weekly entry, pull ideas from
what the relevant `projects/*.md` file lists as typical evidence for
that project (screenshots, PRs, commits, spreadsheets, etc).

Before suggesting any screenshot or file for submission, flag that the
user should crop or mask anything sensitive first: names, emails, phone
numbers, IDs, account info, credentials, or confidential company
information. Never ask the user to paste or store actual passwords, API
keys, or credentials anywhere in the logbook.

### University submission generation

Universities often require the same internship record re-entered into their
own portal: one task-detail field per working day (4,000 characters), one
weekly summary field (4,000 characters) and exactly one attachment. Do not
hand-format that per week - generate it from the logbook that already exists.

Details, profile keys and worked rules: `references/university-submission.md`.
Implementation: `scripts/university_profile.py`, `scripts/logbook_reader.py`,
`scripts/submission_generator.py`, `scripts/char_limit.py`.

Run it rather than estimating:

```bash
python scripts/submission_cli.py --week 13            # copy-ready output
python scripts/submission_cli.py --day 2026-10-28     # one day
python scripts/submission_cli.py --week 13 --validate # checks only
python scripts/submission_cli.py --week 13 --weekly-summary-file draft.txt
python scripts/submission_cli.py --validate-text draft.txt --limit 4000
```

Non-negotiable rules:

1. **Daily records are the only source of daily content.** Read
   `daily/YYYY-MM-DD.md` for every working day in the week; the weekly
   report adds context but never overrides a daily record. Never pull
   activity from another week to fill a gap.
2. **A missing day is a question, not a gap to guess.** Name the exact date,
   leave it out, and ask for the notes. Same for hours: a `TBC` day is
   reported as `NOT RECORDED` - never assume eight hours and never copy the
   previous day's value.
3. **One field per day, consolidated.** If the day held several activities,
   the field describes them together as the work performed; do not split a
   day into multiple submissions.
4. **Character counts are measured, never asserted.** Use
   `char_limit.count_chars` / `check_limit`. Every field is re-measured after
   any shortening, and the number shown is the count of the final text.
   Daily fields keep as much source content as the 4,000 limit allows (the
   condenser refills dropped blocks that still fit); never shorten more than
   the limit forces, and never pad short content.
5. **Shortening deletes, it does not invent.** `fit_to_limit` drops
   low-value blocks and sentences; it never rewrites a claim into a bigger
   one. If a rewrite is needed for readability, write it from the same
   records and validate the final text again.
6. **Exactly one attachment.** Rank real local evidence first
   (`attachments/week-XX/`), then a file named in a daily entry, then a URL,
   then a suggestion. Consolidate several useful files into one PDF only
   when the originals exist and the content survives intact. Never fabricate
   evidence; if nothing exists, say what to capture. Always remind the user
   to strip confidential company information and personal data first.
7. **Nothing is submitted.** The output is copy-ready text for the user's own
   portal. Never claim a portal accepted anything.
8. **The polished weekly summary is part of the first response.** Do not
   present the script's deterministic draft and offer a rewrite later. Read
   the week's records, write the summary yourself (3,500-4,000 characters,
   professional prose, no sentence copied verbatim from a daily field), save
   it to a temp file, and run `--weekly-summary-file` so the final text is
   measured. One request, one complete answer.
9. **Content first, diagnostics last.** The rendered layout puts every
   copy-ready field first (daily blocks, weekly summary, attachment) and
   places validation, counters and notes after an explicit
   `END OF COPY-READY CONTENT` line. Never lead with a validation report.
10. **A missing day keeps its slot and is marked incomplete.** The block
    reads `(INCOMPLETE - NO DAILY RECORD)` with an empty task field and a
    note not to submit it. Still show every other day's real content. Never
    delete the slot, never fill it.

The rendered layout (copy-ready per field, counters outside the text) is
`templates/university-submission-output.md`. Workflow for every request:
read the week's records, write the summary prose yourself, save it, run
`submission_cli.py --week N --weekly-summary-file <file>`, then present that
output as-is. The script measures and fits the real final text; you do not
reformat afterwards.

## Commands

These are natural-language trigger phrases, not slash commands —
the skill's description matches against them when you describe
your task in conversation. No actual `/log` or `/review`
command exists; typing a bare slash gets "Unknown command."

- **Log today's work** — give the agent rough notes like:
  "log today's work: ...", "add today's task: ...", "today I worked on..."
  The agent resolves the date and week, creates or updates
  that day's file, updates the relevant project file(s), suggests attachments.
- **Review today's entry** — ask "review today's entry" or
  "check today's log". The agent re-checks the current day's
  entry for accuracy, repetition, wording, missing info, wrong
  status, unsupported claims, and consistency with the project
  file. Reports and offers fixes.
- **Weekly report** — ask "generate this week's report",
  "give me the weekly report", or "do the weekly". The agent
  runs the weekly-report workflow for the current (or specified) week.
- **University submission** — `/university`, `/submission`, `/submit-week`,
  or "generate my university submission for this week" / "Prepare Week 5
  for university submission" / "give me Monday to Friday task details" /
  "prepare everything I need to copy into the university system". The agent
  runs the submission workflow for the current or named week and presents the
  copy-ready layout with its validation report.
- **One submission day** — `/submit-day` plus a date, or "regenerate
  Wednesday's task detail". Emits that single day's field, measured.
- **Validate a submission** — `/validate-submission`, or "validate week 13
  for submission". Runs the seven checks without regenerating content, and
  lists missing days, missing hours and attachment readiness.
- **Character check** — "is my summary under 4000 characters?" Run
  `submission_cli.py --validate-text <file> --limit 4000`; never answer from
  an estimate.

## Pitfalls

1. **Don't invent dates.** Always resolve the date fresh from what the
   user says plus the real calendar date. Never infer from a previous
   message or assume a new conversation means a new day.

2. **Don't overwrite existing daily files.** When `daily/YYYY-MM-DD.md`
   already exists, merge new information into it — never replace it.

3. **Don't fabricate missing days.** If a weekly report is missing daily
   files for some dates, tell the user which dates are missing and ask
   for the notes. Never fill in a day that doesn't have data.

4. **Don't exaggerate scope.** Vague notes get cleaned up for wording,
   not inflated in scope. "Checked a filter still worked" → "Conducted
   functional testing..." not "Redesigned the architecture."

5. **Google Drive credentials are user-specific.** The `client_secret.json`
   and `token.json` files live at `~/.hermes/` and are excluded from
   `.gitignore` for this reason — never commit them.

6. **Week boundaries follow working days, not calendar Mondays.** If the
   internship starts on a Wednesday, Week 1 runs Wednesday–Tuesday, not
   the calendar week. Recalculate from the actual start date.

7. **Don't hardcode person-specific info in SKILL.md.** The skill is
   generic — personal details belong in `AGENTS.md` or `projects/*.md`,
   not in the procedure file.

8. **Don't state a character count you didn't measure.** Portal limits count
   spaces, punctuation and newlines. Estimate by eye and the field gets
   rejected or truncated at the worst moment. Measure the final text, every
   time.

9. **Don't fill a submission day from another week.** A missing daily record
   stays missing and is named. Reusing last week's activity produces a false
   record a supervisor can check.

10. **Don't recommend two attachments.** The portal takes one. Rank, pick
    one, and mention consolidation only as an option on real files.

## Verification

After logging daily notes, verify:

1. **File created/updated:** `daily/YYYY-MM-DD.md` exists and contains
   the user's raw notes verbatim (preserved in the Raw Notes section).
2. **Date and week correct:** The date matches what the user asked for
   (defaulting to today), and the week number is consistent with
   `AGENTS.md`'s start date.
3. **Project files updated:** Any project mentioned in the notes has
   its `projects/<name>.md` updated with current status.
4. **No fabrication:** Every claim in the entry is traceable to the
   user's raw notes or a previous project file. Status labels match
   the actual progress (Completed / In Progress / Pending Review /
   Pending Merge / Blocked).
5. **No sensitive data in logbook:** The entry doesn't contain passwords,
   API keys, or credentials the user shouldn't be storing in the repo.

After generating a weekly report, verify:

6. **All days present:** Every working day in the week's date range
   has a corresponding daily file, or the missing dates are explicitly
   flagged to the user.
7. **No cross-week contamination:** The report only draws from daily
   files that actually fall inside that week's date range.

After generating a university submission, verify:

8. **Every field measured:** each daily field and the weekly summary has a
   count produced by `char_limit`, and every count shown matches the text
   displayed.
9. **Every day traceable:** each `DAY n` block maps to an existing
   `daily/YYYY-MM-DD.md` record in the same week; missing dates are listed
   rather than skipped silently.
10. **One attachment, honest status:** exactly one recommendation, with
    `Ready` only when the file actually exists locally.
11. **No port of the portal inside the repo:** the run produced text only —
    nothing was uploaded or submitted.

## Reference files

- `assets/AGENTS-template.md` — template for a new user's AGENTS.md
- `assets/daily-template-simple.md` / `assets/daily-template-detailed.md`
  — the two supported daily entry formats
- `assets/project-template.md` — template for a new `projects/<name>.md`
- `references/writing-style.md` — tone guide and before/after examples
- `scripts/config.py` — storage provider configuration (local / google_drive)
- `scripts/google_drive_auth.py` — Google Drive OAuth2 authentication
- `scripts/google_drive_provider.py` — Google Drive storage provider
- `references/google-drive-sync.md` — folder layout, sync commands, token expiry/corruption rules
- `templates/daily-template.md` — generic daily template
- `templates/weekly-template.md` — generic weekly template
- `tests/test_google_drive.py` — mocked integration tests (no real credentials needed)
- `references/university-submission.md` — portal fields, limits, attachment
  ranking, validation rules and the copy-ready layout
- `scripts/university_profile.py` — submission profile (limits, working days,
  holidays, start date) loaded from `config/university-submission.json`
- `scripts/logbook_reader.py` — read-only parser for `daily/` and `weeks/`
- `scripts/submission_generator.py` — daily/weekly composition, attachment
  recommendation, seven validation checks, renderers
- `scripts/char_limit.py` — character counting, limit checks, delete-only
  shortening
- `scripts/submission_cli.py` — CLI for `/university`, `/submit-week`,
  `/submit-day`, `/validate-submission`
- `templates/university-submission.json` — profile template to copy
- `templates/university-submission-output.md` — copy-ready output template
- `tests/test_char_limit.py`, `tests/test_logbook_reader.py`,
  `tests/test_submission_generator.py` — limits, parsing, generation and
  no-fabrication tests
