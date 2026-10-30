# University Submission Generator

Converts an already-written logbook week into the fields a university
internship portal asks for, so the user can copy and paste instead of
reformatting by hand. It never submits anything, and it never invents a day
that is not in `daily/`.

The portal this was built against accepts:

| Field | Limit | Notes |
|-------|-------|-------|
| Daily task details | 4,000 characters | one field per working day, spaces/punctuation/newlines counted |
| Weekly summary | 4,000 characters | one field per week |
| Weekly attachment | exactly 1 file | screenshots, report, PDF |

Both limits and the working-day set are configuration, not code.

## Where the content comes from

| Source | Used for |
|--------|----------|
| `daily/YYYY-MM-DD.md` | primary source of truth for each day's task detail, issue, solution, status, hours, attachments |
| `weeks/week-XX.md` | continuity and the week's own Suggested Attachments list |
| `projects/*.md` | only through the daily text - nothing is pulled from project files directly |
| `attachments/week-XX/` | real evidence files that can be recommended as-is |
| `AGENTS.md` | internship start date, when the profile does not set one |
| `config/university-submission.json` | limits, working days, holidays, output language |

A weekly summary that already exists is **context**, never authority: if it
disagrees with a daily record, the daily record wins.

## Data rules

- **Five daily fields per normal week**, or however many working days the
  profile defines; public holidays reduce the count.
- **Missing day → ask, do not fill.** The generator names the exact dates
  and leaves them out. It never copies a previous week's activity.
- **Multiple activities in one day → one consolidated description.** The
  daily `Task Detail` section is already the consolidation; the generator
  condenses it, it does not re-narrate.
- **Hours come from the `Total Hours` section.** `TBC`, `N/A` or a
  placeholder sentence is reported as `NOT RECORDED`. Eight hours are never
  assumed, and different days may carry different hours.
- **One attachment.** Ranked: local file in `attachments/week-XX/` >
  file named in a daily entry that exists locally > URL named in an entry >
  suggestion text. Multiple local files produce a consolidation note, not
  two recommendations.

## Character counting

`scripts/char_limit.py` is the only place that measures text.

- `count_chars(text)` = `len()` after normalising CRLF to `\n`. Newlines and
  spaces each cost one character; Unicode counts per code point.
- `check_limit(text, 4000)` returns `count`, `remaining`, `over_by` and
  `within_limit`.
- `fit_to_limit(text, limit, target)` shortens by **deleting only**:
  low-value blocks first, then low-value sentences, then a word-boundary cut
  as a last resort. Nothing is added, so a shortened field cannot introduce a
  claim the record did not contain.
- Every generated field is re-measured after shortening. A count that was
  not measured is never displayed.

## Commands

```bash
# whole week, copy-ready layout
python scripts/submission_cli.py --week 13

# current week
python scripts/submission_cli.py

# one day only
python scripts/submission_cli.py --day 2026-10-28

# validation report only
python scripts/submission_cli.py --week 13 --validate

# write the summary yourself, then let the script measure and fit the FINAL text
python scripts/submission_cli.py --week 13 --weekly-summary-file draft-summary.txt

# count any file against a limit
python scripts/submission_cli.py --validate-text draft.txt --limit 4000

# machine-readable
python scripts/submission_cli.py --week 13 --json

# which weeks have data
python scripts/submission_cli.py --list-weeks
```

Exit codes: `0` all checks pass, `1` something needs attention, `2`
configuration/source problem (missing start date, missing daily file for
`--day`).

## Workflow the agent follows

1. Load the profile (`university_profile.load_profile`) and confirm
   `internship_start_date`. If it is absent, ask - do not infer it from the
   first filename.
2. Compute the week from the start date, not from the calendar week number.
3. Collect the week (`LogbookReader.collect_week`) and read every daily
   record plus the weekly report.
4. Run the generator to produce the scaffold: five daily fields, a summary
   draft, one attachment, seven validation checks.
5. Write the weekly summary yourself from the same records - full prose,
   3,500-4,000 characters, no sentence copied from a daily field - save it to
   a temp file, and re-run with `--weekly-summary-file`. The script measures
   and fits the FINAL text; never quote a character count you did not get
   from the script. Do this in the same response as the request: the user
   must not have to ask for a fuller summary afterwards.
6. Present the output verbatim, copy-ready fields first; validation and notes
   come after the `END OF COPY-READY CONTENT` marker.
7. Never submit to the portal. Never claim the portal accepted it.

## Validation checks and what makes them fail

| Check | Fails when |
|-------|-----------|
| Dates | any expected working day has no daily record, duplicate dates, or a weekday label that disagrees with the date |
| Daily task details | a field is empty, or the same text appears on more than one day |
| Character limits | any daily field or the summary exceeds its limit (counted, not estimated) |
| Total hours | any day has no numeric hours (`TBC` included) |
| Weekly summary | empty, over limit, or contains a sentence copied verbatim from a daily field |
| Single attachment | nothing available, or more than one recommended |
| Source accuracy | hours differ from the daily record, a field's wording is not ≥90% traceable to its source, or the summary cites a `BUG-n` that no record in the week contains |

## Attachment guidance to repeat to the user

- Prefer one strong, self-explanatory piece of evidence: a defect list, test
  run summary, annotated screenshot set, or a report PDF.
- Combining several files into one PDF is allowed only when the originals are
  available and the content survives intact - never invent, retouch or
  re-create evidence.
- Remove company-confidential material and personal data (names, emails,
  phone numbers, IDs, credentials, customer records) before uploading.
- If nothing exists, say exactly what to capture this week rather than
  suggesting a file that does not exist.

## Output contract

Order is content first, diagnostics last:

1. heading and period
2. `DAILY TASK DETAILS` - one `DAY n — WEEKDAY` block per working day, each
   with date, total hours, character count outside the text, then the task
   text. A day with no record keeps its block, marked
   `(INCOMPLETE - NO DAILY RECORD)`, with an empty field and a do-not-submit
   note.
3. `WEEKLY SUMMARY` - the authored prose, counted
4. `WEEKLY ATTACHMENT` - one file, reason, status
5. `END OF COPY-READY CONTENT` marker
6. `WARNINGS AND VALIDATION` - the seven checks, holidays, missing days, notes
   and the confidentiality reminder

Counters and explanations never sit inside a field, so every field can be
copied alone. The template is `templates/university-submission-output.md`.

Daily fields are condensed only as far as the 4,000 limit forces: the
condenser drops low-value blocks, then refills any dropped block that still
fits, so the field carries as much real content as possible.

## Configuration

`config/university-submission.json` (git-ignored, per user):

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

Copy `templates/university-submission.json` to start. Load order:
`$UNIVERSITY_SUBMISSION_CONFIG` → `config/university-submission.json` →
defaults (plus a start date from `AGENTS.md`). Another university reuses the
same code by shipping a different profile.
