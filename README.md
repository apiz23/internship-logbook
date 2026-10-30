# Internship Logbook Agent

Turn short, informal daily notes into a structured, university-style
internship / industrial-training / practicum (OJT) logbook — and
generate weekly reports from them automatically.

This started as a personal workflow (`AGENTS.md`) for tracking a
software engineering internship, generalized so anyone can drop it into
their own repo and use it for their own internship, regardless of field
or agent tool.

## What's in this repo

```text
internship-logbook/
├── SKILL.md                          ← the full instructions/prompt
├── AGENTS.md                         ← user identity + timeline (local)
├── scripts/
│   ├── config.py                     ← storage configuration
│   ├── google_drive_auth.py          ← OAuth2 authentication (Hermes-native)
│   ├── google_drive_provider.py      ← Google Drive storage provider
│   ├── google_drive_sync.py          ← Google Drive sync
│   ├── setup_google_drive.py         ← setup wizard
│   ├── char_limit.py                 ← character counting + validation
│   ├── university_profile.py         ← submission profile (limits, days)
│   ├── logbook_reader.py             ← read-only parser for daily/weeks
│   ├── submission_generator.py       ← university submission fields
│   └── submission_cli.py             ← CLI for the submission commands
├── config/
│   └── university-submission.json    ← your portal profile (git-ignored)
├── assets/
│   ├── AGENTS-template.md          ← fill this in once, for yourself
│   ├── daily-template-simple.md    ← lightweight daily entry format
│   ├── daily-template-detailed.md  ← fuller daily entry format
│   └── project-template.md         ← one of these per ongoing project
├── templates/
│   ├── daily-template.md           ← generic daily template
│   └── weekly-template.md          ← generic weekly template
├── references/
│   ├── writing-style.md            ← tone guide + before/after examples
│   └── university-submission.md    ← portal fields, limits, validation
├── templates/
│   ├── university-submission.json  ← profile template
│   └── university-submission-output.md ← copy-ready layout
├── tests/
│   ├── test_google_drive.py        ← mocked integration tests
│   ├── test_char_limit.py          ← counting/limit tests
│   ├── test_logbook_reader.py      ← parser + regression tests
│   └── test_submission_generator.py ← submission generation tests
├── .env.example                      ← environment variable template
└── .gitignore                        ← excludes credentials and personal data
```

Nothing in here is specific to any one person, university, or job —
personal and project details live in files *you* create locally
(`AGENTS.md` and `projects/*.md`), which are never committed with
someone else's info in them.

## Install

### Option A — Hermes (recommended)

1. Clone the repo:
   ```bash
   git clone <repo-url>
   cd internship-logbook
   ```
2. Install the skill into Hermes:
   ```bash
   cp -r skills/internship-logbook ~/.hermes/skills/personal/
   ```
3. Set up your repo:
   ```bash
   cp skills/internship-logbook/assets/AGENTS-template.md AGENTS.md
   # Edit AGENTS.md with your name, institution, start date, etc.
   mkdir -p daily weeks projects attachments
   ```
4. Enable Google Drive (optional) — see [Google Drive Authentication](#google-drive-authentication) below.
5. Start logging: give the agent your rough end-of-day notes and it
   creates/updates `daily/YYYY-MM-DD.md` for you automatically.

### Option B — Manual (any agent)

1. Clone the repo.
2. Copy `SKILL.md` and the `assets/` files into your agent's skill directory (or paste `SKILL.md` into your agent's instructions).
3. Fill in `AGENTS.md` from `assets/AGENTS-template.md`.
4. Create `daily/`, `weeks/`, `projects/`, `attachments/` folders.
5. Give the agent your rough notes — it handles the rest.

### Skill triggering

Skill-triggering depends on the agent tool. Some tools support explicit
invocation (a slash command, a "use skill X" call); others rely entirely
on matching the task description in natural conversation. If a phrase
doesn't trigger it, try explicitly naming the skill in your request
(e.g. "use the internship-logbook skill to log today's work: ...").

## Using it with Claude (as a Skill)

If you're on Claude.ai / Claude Code / Cowork with Skills enabled,
install this folder as a Skill (via the `.skill` file, if provided, or
by pointing Claude at this folder and asking it to add it as a skill).
Claude will then automatically read `SKILL.md` whenever you mention a
logbook, "log today's work", "review today's entry", or
"generate this week's report".

## Using it with another agent (Hermes, ChatGPT, etc.)

This isn't Claude-specific. Some agents (Hermes included) recognize
`AGENTS.md` and `SKILL.md` as two different kinds of file, and it's
worth keeping that distinction rather than merging them:

- **`AGENTS.md`** — stable facts, always loaded: your name, institution,
  internship timeline, and real project details. Copy
  `assets/AGENTS-template.md` → `AGENTS.md` at your repo root and fill
  it in with your own info.
- **`SKILL.md`** — the procedure, loaded for logbook-type work: date/week
  calculation, one-file-per-date rule, accuracy rules, weekly report
  format. Drop this file into the repo as-is.

If your agent doesn't distinguish the two (or just takes one system
prompt), concatenate them — `AGENTS.md` first, then `SKILL.md` — and
paste the combined text in as its instructions.

Either way, make sure the agent has read/write access to your
`AGENTS.md`, `daily/`, `weeks/`, and `projects/` files (however that
tool exposes local files — repo context, uploaded files, a connected
filesystem, etc), then use it the same way: give it rough notes, ask
for the log, a review, or a weekly report.

## Core principles (see `SKILL.md` for full detail)

- **Raw notes are the source of truth** — never deleted or silently
  rewritten, only appended to.
- **One date, one file** — no duplicate daily files for the same day.
- **No fabrication** — the agent won't invent finished work, resolved
  bugs, merged PRs, or issues that weren't actually mentioned. If a
  week is missing days, it says so instead of filling them in.
- **Wording gets more professional, not more impressive** — vague notes
  get cleaned up, not exaggerated in scope.

## Customizing for your own field

This was written by a software engineering intern, so the examples in
`references/writing-style.md` lean technical — but the workflow itself
(notes → daily file → project continuity → weekly report) is generic.
Adjust `AGENTS.md`'s "Notes" field and your `projects/*.md` files for
whatever your actual work is (data analysis, design, marketing, lab
research, etc.) — you shouldn't need to touch `SKILL.md` itself.

## University Submission Generator

Many universities make you re-enter your internship record in their own
portal: one task-detail field per working day, one weekly summary, one
attachment. This generates all of it from the logbook you already keep, with
the character limits enforced and counted.

### Commands

| Command | What it does |
|---------|--------------|
| `/university` | Complete submission for the current or specified week |
| `/submission` | Copy-ready submission fields |
| `/submit-week` | Alias for a complete weekly submission |
| `/submit-day` | Regenerate one day's task detail |
| `/validate-submission` | Limits, dates, hours, missing records, attachment readiness |

Natural language works too: "generate my university submission for this
week", "prepare Week 5 for university submission", "give me Monday to Friday
task details", "weekly summary under 4000 characters", "prepare everything I
need to copy into the university system".

### Direct CLI use

```bash
python scripts/submission_cli.py --week 13            # copy-ready layout
python scripts/submission_cli.py                      # current week
python scripts/submission_cli.py --day 2026-10-28      # one day
python scripts/submission_cli.py --week 13 --validate  # checks only
python scripts/submission_cli.py --week 13 --weekly-summary-file draft.txt
python scripts/submission_cli.py --validate-text draft.txt --limit 4000
python scripts/submission_cli.py --week 13 --json
```

### Output

```text
UNIVERSITY INTERNSHIP SUBMISSION — WEEK 13
...
DAY 1 — MONDAY
Date: 2026-10-26
Total Hours: 8 hours
Character Count: 3703 / 4000

TASK DETAILS:
[text you paste - no counters, no headings inside it]
...
WEEKLY SUMMARY
Character Count: 1035 / 4000
...
WEEKLY ATTACHMENT
Recommended File: attachments/week-13/otalk-issue-list-2026-10-26.md
Reason: Local evidence file in the week folder (md, 2941 bytes).
Upload Status: Ready
...
END OF COPY-READY CONTENT
[everything above is submission text]
========================================
WARNINGS AND VALIDATION
- Dates: NEEDS ATTENTION — missing daily record(s): 2026-10-30 (Friday)
- Daily task details: PASS
- Character limits: PASS
- Total hours: PASS
- Weekly summary: PASS
- Single attachment: PASS
- Source accuracy: PASS
```

### Experience

One request produces the whole submission. The weekly summary is written from
the week's records in the same response - you never have to ask for a fuller
version. Content comes first; validation and notes sit after an
`END OF COPY-READY CONTENT` marker so nothing diagnostic lands in a paste. A
missing day keeps its block, marked `(INCOMPLETE - NO DAILY RECORD)`, with an
empty field and a do-not-submit note.

### What it will not do

- It will not invent a day that has no `daily/YYYY-MM-DD.md`; it names the
  date and asks for the notes.
- It will not assume 8 hours when `Total Hours` says `TBC`.
- It will not claim a character count it did not measure.
- It will not fabricate or retouch evidence, and it recommends at most one
  attachment.
- It will not submit anything to the portal - the text is for you to paste.

### Configuration

Copy `templates/university-submission.json` to
`config/university-submission.json` (git-ignored) and set at least
`internship_start_date`. Limits, working days, holidays and output language
live there, not in `SKILL.md`:

```json
{
  "submission_enabled": true,
  "daily_task_char_limit": 4000,
  "weekly_summary_char_limit": 4000,
  "target_min_chars": 3500,
  "target_max_chars": 3800,
  "working_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
  "daily_fields": ["date", "task_details", "total_hours"],
  "weekly_fields": ["weekly_summary", "attachment"],
  "max_weekly_attachments": 1,
  "output_language": "en",
  "internship_start_date": "YYYY-MM-DD",
  "public_holidays": {"YYYY-MM-DD": "Holiday name"}
}
```

If the profile has no start date, it is read from an
`Internship start date: YYYY-MM-DD` line in `AGENTS.md`. Another university
reuses the same code by shipping a different profile.

### Tests

```bash
python -m pytest tests/test_char_limit.py tests/test_logbook_reader.py \
                 tests/test_submission_generator.py -q
```

Covers exact 4,000 / 4,001 boundaries, spaces, newlines, punctuation and
Unicode, five-day weeks, public holidays, shorter weeks, missing records,
missing hours, multiple activities in one day, summary accuracy and limit,
single-attachment selection, and residue checks that existing daily/weekly
workflows still parse.

## Google Drive Authentication

The Internship Logbook supports Google Drive storage via Hermes' native
Google Workspace OAuth flow. Each user authenticates their own Google
account — no shared credentials, no hardcoded tokens.

### Prerequisites

1. **Hermes Agent** installed and available on your PATH:
   ```bash
   hermes --version
   ```
   If not installed: https://hermes-agent.nousresearch.com/docs/

2. **Google Cloud Project** with the Google Drive API enabled:
   - Go to [console.cloud.google.com](https://console.cloud.google.com)
   - Create a project (or use an existing one)
   - Enable the **Google Drive API** in the API Library

3. **OAuth 2.0 Client ID** (Desktop app type):
   - Go to [console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials)
   - Credentials → Create Credentials → OAuth 2.0 Client ID
   - Application type: **Desktop app**
   - Download the JSON file

### Setup (one command)

After cloning the repo:

```bash
git clone <repo-url>
cd internship-logbook

# Place your client_secret.json at ~/.hermes/google_client_secret.json
# (or anywhere — the setup script will prompt you)

python scripts/setup_google_drive.py
```

The setup script will:
1. Detect if Hermes and the Google Workspace skill are installed
2. Walk you through OAuth authorization (opens a browser)
3. Save your token to `~/.hermes/google_token.json`
4. Verify Drive API access with a test call

### Manual setup (if Hermes Google Workspace is not available)

If Hermes' Google Workspace skill is not installed, the setup script
falls back to a standard Google OAuth flow:

```bash
# 1. Place client_secret.json at ~/.hermes/google_client_secret.json
python scripts/setup_google_drive.py

# Or manually:
# 2. Get authorization URL
python ${HERMES_HOME:-$HOME/.hermes}/skills/productivity/google-workspace/scripts/setup.py --auth-url --services drive --format json

# 3. Visit the URL, authorize, paste the redirect URL back
# 4. Verify
python scripts/setup_google_drive.py --check
```

### Enable Google Drive storage

Set the environment variables:

**macOS / Linux:**
```bash
export STORAGE_PROVIDER=google_drive
export GOOGLE_DRIVE_ROOT_FOLDER_ID=YOUR_GOOGLE_DRIVE_FOLDER_ID
```

**Windows (PowerShell):**
```powershell
$env:STORAGE_PROVIDER="google_drive"
$env:GOOGLE_DRIVE_ROOT_FOLDER_ID="YOUR_GOOGLE_DRIVE_FOLDER_ID"
```

Or create `scripts/config.json`:
```json
{
  "provider": "google_drive",
  "google_drive": {
    "enabled": true,
    "root_folder_id": "YOUR_GOOGLE_DRIVE_ROOT_FOLDER_ID"
  }
}
```

### How another developer authenticates their own account

Each developer follows the same steps with **their own** Google account:

1. Create their own Google Cloud project
2. Enable the Drive API in their own project
3. Create their own OAuth 2.0 Desktop client credentials
4. Download `client_secret.json` and place it at `~/.hermes/google_client_secret.json`
5. Run `python scripts/setup_google_drive.py`
6. Authorize in the browser (their own Google account)
7. The token is saved to their own `~/.hermes/google_token.json`

No repository files are modified. No shared credentials.

### What must NEVER be committed to Git

The following are **user-specific secrets** and must never be committed:

- `~/.hermes/google_client_secret.json` — OAuth client credentials
- `~/.hermes/google_token.json` — OAuth access/refresh tokens
- `token.json` — any OAuth token file
- `*.token.json` — token files
- `.env` — environment variables with secrets
- `scripts/config.json` — if it contains real folder IDs

The `.gitignore` already excludes these. Verify with:
```bash
git status
```

### Where credentials are stored

| File | Purpose | Location |
|------|---------|----------|
| `google_client_secret.json` | OAuth client credentials (one-time download) | `~/.hermes/` |
| `google_token.json` | OAuth access + refresh tokens (auto-refreshed) | `~/.hermes/` |

Both paths respect the `HERMES_HOME` environment variable if set.

### Getting your Google Drive folder ID

1. Open Google Drive in a browser
2. Navigate to the folder where you want logbook files stored
3. Copy the folder ID from the URL:
   ```
   https://drive.google.com/drive/folders/FOLDER_ID_HERE
   ```
4. Set it as `GOOGLE_DRIVE_ROOT_FOLDER_ID`

### Troubleshooting

| Problem | Fix |
|---------|-----|
| `Hermes Google Workspace skill was not found` | Install Hermes and the google-workspace skill, or use the manual OAuth fallback |
| `No token file found` | Run `python scripts/setup_google_drive.py` |
| `Token expired` | Re-run the setup script; tokens auto-refresh if a refresh token exists |
| `Auth verification failed` | Make sure the Drive API is enabled in your Google Cloud project |
| `Invalid credentials` | Delete `~/.hermes/google_token.json` and re-run setup |
| `Access Not Configured` | Enable Google Drive API in your Google Cloud Console |
| `HttpError 403` | Re-authorize with Drive scope: run setup script again |

### Security

- Credentials are stored in `~/.hermes/` (user home), **never** in the repo
- OAuth tokens are automatically refreshed — no manual token management
- The app uses the narrow `https://www.googleapis.com/auth/drive` scope only
- No credentials, tokens, or secrets are printed in logs or console output
- If you suspect a token is compromised, delete `~/.hermes/google_token.json` and re-run setup

## Storage Providers

The Internship Logbook supports two storage backends:

### Local Storage (default)

Markdown files are stored locally in the repository:
- `daily/YYYY/MM/YYYY-MM-DD.md`
- `weeks/YYYY/Week-XX.md`
- `projects/<project-name>.md`

No configuration needed — this is the default.

### Google Drive Storage

Markdown files are stored in your Google Drive folder (configured as above).

#### Folder Structure

When Google Drive is enabled, files are stored in:
```
internship-logbook/
├── daily/YYYY/MM/YYYY-MM-DD.md
├── weekly/YYYY/Week-XX.md
├── monthly/YYYY/YYYY-MM.md
└── templates/
```

#### Disabling Google Drive

Set `STORAGE_PROVIDER=local` or remove the environment variable.
The skill continues to work with local storage.

## Other Hermes users

Anyone can configure their own Google Drive integration:

1. Clone this repo
2. Create a Google Cloud project with Drive API enabled
3. Download `client_secret.json` and place at `~/.hermes/google_client_secret.json`
4. Run `python scripts/setup_google_drive.py`
5. Set `GOOGLE_DRIVE_ROOT_FOLDER_ID` to your own Drive folder ID
6. The skill works the same for everyone — no source code changes needed

## License

MIT — use, modify, and share freely. Remove or change this section if
you'd prefer a different license for your fork.
