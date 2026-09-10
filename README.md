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
│   ├── google_drive_auth.py          ← OAuth2 authentication
│   └── google_drive_provider.py      ← Google Drive storage provider
├── assets/
│   ├── AGENTS-template.md          ← fill this in once, for yourself
│   ├── daily-template-simple.md    ← lightweight daily entry format
│   ├── daily-template-detailed.md  ← fuller daily entry format
│   └── project-template.md         ← one of these per ongoing project
├── templates/
│   ├── daily-template.md           ← generic daily template
│   └── weekly-template.md          ← generic weekly template
├── references/
│   └── writing-style.md            ← tone guide + before/after examples
├── tests/
│   ├── test_google_drive.py        ← mocked integration tests
└── .gitignore                      ← excludes credentials and personal data
```

Nothing in here is specific to any one person, university, or job —
personal and project details live in files *you* create locally
(`AGENTS.md` and `projects/*.md`), which are never committed with
someone else's info in them.

## Quick start

1. **Clone or download this repo** (or just copy the files into your
   internship notes repo).
2. Copy `assets/AGENTS-template.md` → `AGENTS.md` at the repo root, and
   fill in your name, institution, internship start date, working days,
   and which daily template style you want.
3. Create a `daily/`, `weeks/`, `projects/`, and `attachments/` folder
   (or let your agent create them the first time you use it — see
   `SKILL.md`'s "Repository layout" section).
4. Start logging: give the agent your rough end-of-day notes and it
   creates/updates `daily/YYYY-MM-DD.md` for you, working out the date
   and internship week automatically from `AGENTS.md`.
5. Ask for a weekly report whenever you want one — it's built only from
   verified daily files, and it'll tell you if a day is missing instead
   of making one up.

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

## Storage Providers

The Internship Logbook supports two storage backends:

### Local Storage (default)

Markdown files are stored locally in the repository:
- `daily/YYYY/MM/YYYY-MM-DD.md`
- `weeks/YYYY/Week-XX.md`
- `projects/<project-name>.md`

No configuration needed — this is the default.

### Google Drive Storage

Markdown files are stored in your Google Drive folder.

#### Prerequisites

1. **Google Cloud Project**: Create a project at
   [console.cloud.google.com](https://console.cloud.google.com).

2. **Enable Google Drive API**: In the API Library, enable the
   Google Drive API.

3. **Create OAuth Credentials**: Go to Credentials → Create Credentials
   → OAuth 2.0 Client ID → Desktop app. Download the
   `client_secret.json` file.

4. **Place credentials**: Put `client_secret.json` at:
   ```
   ~/.hermes/google_client_secret.json
   ```

5. **Authorize**: Run the authentication script:
   ```bash
   python scripts/google_drive_auth.py
   ```
   This opens a browser for you to authorize the app. The token is
   saved to `~/.hermes/google_token.json`.

   To verify authentication and folder access:
   ```bash
   STORAGE_PROVIDER=google_drive \
   GOOGLE_DRIVE_ROOT_FOLDER_ID=<your-folder-id> \
   PYTHONPATH=scripts \
   python3 scripts/google_drive_auth.py --test
   ```

#### Enabling Google Drive

Set the `STORAGE_PROVIDER` environment variable:
```bash
export STORAGE_PROVIDER=google_drive
export GOOGLE_DRIVE_ROOT_FOLDER_ID=YOUR_GOOGLE_DRIVE_ROOT_FOLDER_ID
```

Or create a `scripts/config.json`:
```json
{
  "provider": "google_drive",
  "google_drive": {
    "enabled": true,
    "root_folder_id": "YOUR_GOOGLE_DRIVE_ROOT_FOLDER_ID"
  }
}
```

#### Folder Structure

When Google Drive is enabled, files are stored in:
```
internship-logbook/
├── daily/YYYY/MM/YYYY-MM-DD.md
├── weekly/YYYY/Week-XX.md
├── monthly/YYYY/YYYY-MM.md
└── templates/
```

#### Security

- **Credentials never leave your machine**: `google_client_secret.json`
  and `google_token.json` are stored at `~/.hermes/` and are excluded
  from `.gitignore`.
- **No hardcoded credentials**: The repository uses placeholder
  `YOUR_GOOGLE_DRIVE_ROOT_FOLDER_ID`.
- **Narrow scope**: The OAuth token uses only `https://www.googleapis.com/auth/drive`
  — the app can access files within the configured root folder.
- **Tokens are not logged**: No credentials or tokens are printed
  in logs, reports, or console output.

#### Disabling Google Drive

Set `STORAGE_PROVIDER=local` or remove the environment variable.
The skill continues to work with local storage.

## Other Hermes users

Anyone can configure their own Google Drive integration:

1. Clone this repo
2. Create a Google Cloud project with Drive API enabled
3. Download `client_secret.json` and place at `~/.hermes/google_client_secret.json`
4. Run `python scripts/google_drive_auth.py`
5. Set `GOOGLE_DRIVE_ROOT_FOLDER_ID` to your own Drive folder ID
6. The skill works the same for everyone — no source code changes needed

## License

MIT — use, modify, and share freely. Remove or change this section if
you'd prefer a different license for your fork.
