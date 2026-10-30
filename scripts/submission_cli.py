"""CLI for the university submission generator.

Examples
--------
Generate the current week::

    python scripts/submission_cli.py

Generate a specific week::

    python scripts/submission_cli.py --week 13

Regenerate one day::

    python scripts/submission_cli.py --day 2026-10-28

Validate only (no rendering)::

    python scripts/submission_cli.py --week 13 --validate

Validate a weekly summary you wrote yourself (measures the FINAL text)::

    python scripts/submission_cli.py --week 13 --weekly-summary-file draft.txt

Count characters of any file against a limit::

    python scripts/submission_cli.py --validate-text draft.txt --limit 4000

Machine-readable output for another tool::

    python scripts/submission_cli.py --week 13 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from char_limit import check_limit, count_chars, fit_to_limit  # noqa: E402
from logbook_reader import LogbookError  # noqa: E402
from submission_generator import (  # noqa: E402
    SubmissionGenerator,
    render_day_only,
    render_submission,
    render_validation,
)
from university_profile import ProfileError, load_profile  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="submission_cli",
        description="Generate copy-ready university internship submission fields.",
    )
    p.add_argument("--root", default=str(REPO_ROOT), help="logbook repository root")
    p.add_argument("--config", default=None, help="path to a submission profile JSON")
    p.add_argument("--week", type=int, default=None, help="internship week number")
    p.add_argument("--day", default=None, help="single date, YYYY-MM-DD")
    p.add_argument("--validate", action="store_true", help="validation report only")
    p.add_argument(
        "--weekly-summary-file",
        default=None,
        help="use this file as the weekly summary, then measure and fit the final text",
    )
    p.add_argument(
        "--validate-text",
        default=None,
        help="measure one file against --limit and exit",
    )
    p.add_argument("--limit", type=int, default=4000, help="limit for --validate-text")
    p.add_argument("--json", action="store_true", help="emit JSON instead of the portal layout")
    p.add_argument("--list-weeks", action="store_true", help="list weeks with daily records")
    return p


def submission_to_dict(sub) -> dict:
    return {
        "week": sub.week,
        "period": {"start": sub.start.isoformat(), "end": sub.end.isoformat()},
        "daily": [
            {
                "index": i,
                "weekday": d.weekday,
                "date": d.day.isoformat(),
                "total_hours": d.hours,
                "task_details": d.task_text,
                "character_count": d.count,
                "character_limit": d.fit.limit,
                "within_limit": d.within_limit,
                "source": d.source_path,
            }
            for i, d in enumerate(sub.dailies, start=1)
        ],
        "weekly_summary": sub.weekly_summary,
        "weekly_summary_character_count": sub.summary_count,
        "weekly_summary_limit": sub.profile.weekly_summary_char_limit,
        "attachment": {
            "filename": sub.attachment.filename,
            "reason": sub.attachment.reason,
            "status": sub.attachment.status,
            "local_path": sub.attachment.local_path,
            "candidates_considered": sub.attachment.candidates_considered,
            "note": sub.attachment.consolidation_note,
        },
        "validation": [
            {"check": c.name, "status": c.status, "detail": c.detail} for c in sub.checks
        ],
        "overall": "PASS" if sub.ok else "NEEDS ATTENTION",
        "holidays": sub.holidays,
        "missing_days": sub.missing_days,
        "notes": sub.notes,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.validate_text:
        path = Path(args.validate_text)
        if not path.is_file():
            print(f"error: {path} does not exist", file=sys.stderr)
            return 2
        text = path.read_text(encoding="utf-8")
        result = check_limit(text, args.limit)
        print(result.summary())
        if not result.within_limit:
            fitted = fit_to_limit(text, limit=args.limit)
            print(f"after automatic shortening: {fitted.final_count} / {args.limit}")
            if args.json:
                print(json.dumps({"count": result.count, "limit": result.limit,
                                  "within_limit": result.within_limit,
                                  "fitted_count": fitted.final_count}, indent=2))
            return 1
        return 0

    try:
        profile = load_profile(args.root, args.config)
        generator = SubmissionGenerator(args.root, profile)
    except (ProfileError, LogbookError) as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    if args.list_weeks:
        for week in generator.reader.available_weeks():
            start = generator.reader.week_start(week)
            print(f"week-{week:02d}  start {start.isoformat()}")
        return 0

    if args.day:
        try:
            day = date.fromisoformat(args.day)
        except ValueError:
            print(f"error: --day must be YYYY-MM-DD, got {args.day!r}", file=sys.stderr)
            return 2
        try:
            sub = generator.generate_day(day)
        except (FileNotFoundError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        week = generator.reader.week_number_for(day)
        collection = generator.reader.collect_week(week)
        expected = [d for d in collection.expected_days]
        index = expected.index(day) + 1 if day in expected else 1
        print(render_day_only(sub, profile.daily_task_char_limit, index=index))
        print(f"Week: {week}")
        print(f"Character count: {sub.count} / {profile.daily_task_char_limit}")
        print(f"Remaining: {profile.daily_task_char_limit - sub.count}")
        return 0 if sub.within_limit else 1

    try:
        week = args.week or generator.reader.current_week()
        summary_text = None
        if args.weekly_summary_file:
            summary_text = Path(args.weekly_summary_file).read_text(encoding="utf-8")
        submission = generator.generate(week=week, summary_text=summary_text)
    except (ProfileError, LogbookError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(submission_to_dict(submission), indent=2, ensure_ascii=False))
    elif args.validate:
        print(render_validation(submission))
    else:
        print(render_submission(submission))
    return 0 if submission.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
