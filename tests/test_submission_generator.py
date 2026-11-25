"""Tests for the university submission generator (structure and honesty).

Fixtures build a throwaway logbook so the tests never read or write the
user's real records.
"""

import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from char_limit import check_limit, count_chars  # noqa: E402
from logbook_reader import LogbookReader, parse_hours  # noqa: E402
from submission_generator import (  # noqa: E402
    ATTENTION,
    PASS,
    SubmissionGenerator,
    compose_daily_task,
    render_submission,
    to_plain_text,
)
from university_profile import (  # noqa: E402
    ProfileError,
    load_profile,
    parse_start_date_from_agents_md,
)

START = date(2026, 8, 3)  # a Monday


def daily_md(
    day: str,
    weekday: str,
    task: str,
    hours: str | None = "8 hours",
    issue: str = "No blocking issue was identified during this task.",
    solution: str = "Continue with the planned verification.",
    status: str = "Completed",
    attachments: str = "",
) -> str:
    hours_block = hours if hours is not None else "TBC — hours for the day not stated."
    parts = [
        f"# {day} ({weekday})",
        "",
        "## Raw Notes",
        "",
        "- rough note for the day",
        "",
        "## Task Detail",
        "",
        task,
        "",
        "## Issue",
        "",
        issue,
        "",
        "## Proposed Solution",
        "",
        solution,
        "",
        "## Status",
        "",
        status,
        "",
        "## Total Hours",
        "",
        hours_block,
    ]
    if attachments:
        parts += ["", "## Attachments", "", attachments]
    return "\n".join(parts) + "\n"


def make_repo(tmp_path: Path, days: dict[date, str], start: date = START) -> Path:
    root = tmp_path / "repo"
    (root / "daily").mkdir(parents=True)
    (root / "weeks").mkdir()
    (root / "attachments").mkdir()
    (root / "config").mkdir()
    (root / "config" / "university-submission.json").write_text(
        json.dumps(
            {
                "internship_start_date": start.isoformat(),
                "working_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
            }
        ),
        encoding="utf-8",
    )
    for day, content in days.items():
        (root / "daily" / f"{day.isoformat()}.md").write_text(content, encoding="utf-8")
    return root


def five_day_week(
    root: Path, week_start: date = START, overrides: dict[int, dict] | None = None
) -> dict[date, str]:
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    from datetime import timedelta

    overrides = overrides or {}
    days = {}
    for i, name in enumerate(names):
        day = week_start + timedelta(days=i)
        kwargs = dict(
            task=(
                f"Conducted functional testing of the {name.lower()} feature set, "
                f"logged the results and recorded defects BUG-{100 + i}."
            ),
            status="Completed" if i % 2 == 0 else "In Progress",
        )
        if i in overrides:
            kwargs.update(overrides[i])
        days[day] = daily_md(day.isoformat(), name, **kwargs)
    return days


# ---------------------------------------------------------------------------
# Profile and reader
# ---------------------------------------------------------------------------


def test_start_date_scraped_from_agents_md(tmp_path):
    (tmp_path / "AGENTS.md").write_text(
        "# AGENTS.md\n\n- **Internship start date:** 2026-08-03\n", encoding="utf-8"
    )
    profile = load_profile(tmp_path)
    assert profile.internship_start_date == START


def test_start_date_parser_ignores_unrelated_dates():
    text = "Example: `daily/2026-09-07.md`\nUpdated 2026-09-01\n"
    assert parse_start_date_from_agents_md(text) is None


def test_missing_start_date_is_a_clear_error(tmp_path):
    profile = load_profile(tmp_path)
    with pytest.raises(ProfileError, match="start date"):
        profile.validate()


def test_profile_rejects_more_than_one_attachment(tmp_path):
    root = make_repo(tmp_path, {})
    cfg = root / "config" / "university-submission.json"
    data = json.loads(cfg.read_text())
    data["max_weekly_attachments"] = 3
    cfg.write_text(json.dumps(data))
    with pytest.raises(ProfileError, match="exactly one attachment"):
        load_profile(root).validate()


def test_week_number_anchors_on_start_date(tmp_path):
    root = make_repo(tmp_path, five_day_week(tmp_path))
    reader = LogbookReader(root, load_profile(root))
    assert reader.week_number_for(START) == 1
    assert reader.week_number_for(date(2026, 8, 7)) == 1
    assert reader.week_number_for(date(2026, 8, 10)) == 2


def test_parse_hours_rejects_placeholders():
    assert parse_hours("8 hours") == 8
    assert parse_hours("7.5 hours") == 7.5
    assert parse_hours("TBC — hours for the day not stated; correct before submission.") is None
    assert parse_hours("") is None


# ---------------------------------------------------------------------------
# Daily submissions
# ---------------------------------------------------------------------------


def test_five_day_week_generates_five_daily_fields(tmp_path):
    root = make_repo(tmp_path, five_day_week(tmp_path))
    gen = SubmissionGenerator(root, load_profile(root))
    sub = gen.generate(week=1)
    assert len(sub.dailies) == 5
    assert [d.weekday for d in sub.dailies] == [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
    ]
    assert all(d.within_limit for d in sub.dailies)
    assert all(d.task_text for d in sub.dailies)


def test_multiple_activities_on_one_day_are_consolidated_into_one_field(tmp_path):
    task = (
        "Reviewed the defect tracker and confirmed BUG-11 was still reproducible.\n\n"
        "Wrote three regression test cases for the school filter and ran them.\n\n"
        "Updated the project notes with the new case identifiers."
    )
    root = make_repo(
        tmp_path,
        {START: daily_md(START.isoformat(), "Monday", task)},
    )
    sub = SubmissionGenerator(root, load_profile(root)).generate(week=1)
    complete = [d for d in sub.dailies if not d.incomplete]
    assert len(complete) == 1
    text = complete[0].task_text
    assert "BUG-11" in text and "three regression test cases" in text and "project notes" in text
    assert count_chars(text) == complete[0].count


def test_long_task_detail_is_shortened_and_final_text_measured(tmp_path):
    long_task = "\n\n".join(
        f"Step {i}: ran the regression suite against the staging build and recorded "
        f"every failure with BUG-{500 + i} in the tracker." for i in range(60)
    )
    root = make_repo(tmp_path, {START: daily_md(START.isoformat(), "Monday", long_task)})
    profile = load_profile(root)
    sub = SubmissionGenerator(root, profile).generate(week=1)
    day = sub.dailies[0]
    assert count_chars(long_task) > 4000
    assert day.count <= profile.daily_task_char_limit
    # A 4,000-character source is condensed, not filled up to the portal
    # ceiling; a busy day may reach the detailed allowance.
    assert day.count <= profile.daily_task_detailed_max
    assert day.band in {"Concise", "Detailed"}
    assert day.count == count_chars(day.task_text)


def test_missing_working_hours_are_not_assumed(tmp_path):
    root = make_repo(
        tmp_path,
        {START: daily_md(START.isoformat(), "Monday", "Tested the login flow.", hours=None)},
    )
    sub = SubmissionGenerator(root, load_profile(root)).generate(week=1)
    day = sub.dailies[0]
    assert day.hours is None
    assert day.hours_text == "NOT RECORDED"
    hours_check = next(c for c in sub.checks if c.name == "Total hours")
    assert hours_check.status == ATTENTION
    assert "not assumed" in hours_check.detail


def test_different_hours_per_day_are_preserved(tmp_path):
    days = five_day_week(
        tmp_path,
        overrides={
            1: {"hours": "4 hours"},
            3: {"hours": "7.5 hours"},
        },
    )
    root = make_repo(tmp_path, days)
    sub = SubmissionGenerator(root, load_profile(root)).generate(week=1)
    assert [d.hours for d in sub.dailies] == [8.0, 4.0, 8.0, 7.5, 8.0]
    assert sub.dailies[1].hours_text == "4 hours"
    assert sub.dailies[3].hours_text == "7.5 hours"


# ---------------------------------------------------------------------------
# Missing records, holidays, shorter weeks
# ---------------------------------------------------------------------------


def test_missing_daily_record_is_named_not_invented(tmp_path):
    days = five_day_week(tmp_path)
    thursday = date(2026, 8, 6)
    del days[thursday]
    root = make_repo(tmp_path, days)
    sub = SubmissionGenerator(root, load_profile(root)).generate(week=1)
    # The slot is kept so the gap is visible, but it carries no invented text.
    assert len(sub.dailies) == 5
    incomplete = [d for d in sub.dailies if d.incomplete]
    assert [d.day for d in incomplete] == [thursday]
    assert incomplete[0].task_text == ""
    assert incomplete[0].hours is None
    assert thursday.isoformat() in sub.missing_days
    dates_check = next(c for c in sub.checks if c.name == "Dates")
    assert dates_check.status == ATTENTION
    assert thursday.isoformat() in dates_check.detail
    rendered = render_submission(sub)
    assert "INCOMPLETE - NO DAILY RECORD" in rendered
    assert "Do not submit this day" in rendered


def test_public_holiday_reduces_expected_days(tmp_path):
    days = five_day_week(tmp_path)
    friday = date(2026, 8, 7)
    days[friday] = daily_md(
        friday.isoformat(),
        "Friday",
        "Public Holiday — National Day. No work / Cuti.",
        hours="0 hours",
        status="Completed",
    )
    root = make_repo(tmp_path, days)
    sub = SubmissionGenerator(root, load_profile(root)).generate(week=1)
    assert len(sub.dailies) == 4
    assert all(not d.incomplete for d in sub.dailies)
    assert friday.isoformat() in sub.holidays
    assert sub.missing_days == []
    assert next(c for c in sub.checks if c.name == "Dates").status == PASS


def test_four_day_working_week_profile(tmp_path):
    root = make_repo(tmp_path, five_day_week(tmp_path))
    cfg = root / "config" / "university-submission.json"
    data = json.loads(cfg.read_text())
    data["working_days"] = ["Monday", "Tuesday", "Wednesday", "Thursday"]
    cfg.write_text(json.dumps(data))
    profile = load_profile(root)
    sub = SubmissionGenerator(root, profile).generate(week=1)
    assert len(sub.dailies) == 4
    assert all(not d.incomplete for d in sub.dailies)
    assert sub.missing_days == []


# ---------------------------------------------------------------------------
# Weekly summary, attachment, validation, rendering
# ---------------------------------------------------------------------------


def rich_week(root: Path) -> dict[date, str]:
    """A week with findings, defects and blockers worth summarising."""
    from datetime import timedelta

    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    topics = [
        "Executed the regression pass on the O'Care school filter and confirmed the "
        "filtered list matched the selected school. Two mismatched records were "
        "reproduced and reported as BUG-201, and the remaining checks passed.",
        "Reviewed the O'Zone upload module on the staging build. Large file upload "
        "worked, but a video with several subtitle files kept only the first one, "
        "which was reported as BUG-202 and blocked the subtitle regression checks.",
        "Documented the test cases written during the week and updated the tracker "
        "with the recorded outcomes. Thirteen cases moved to Done after verification.",
        "Investigated the invitation flow and found that an already-registered "
        "address consumed the invitation without creating an account, reported as "
        "BUG-203. The fix was not available, so the case stayed blocked.",
        "Ran the suspension and appeal checks on staging, confirmed the session "
        "cut-off and the appeal round trip, and closed four cases. Reviewed the "
        "defect list with the supervisor and agreed the remaining work for next week.",
    ]
    days = {}
    for i, name in enumerate(names):
        day = START + timedelta(days=i)
        days[day] = daily_md(
            day.isoformat(),
            name,
            topics[i],
            issue=f"A blocking defect limited coverage on {name}: BUG-20{i} stayed open.",
            solution="Recorded the blocker and continued with the unaffected checks.",
            status="In Progress" if i % 2 else "Completed",
        )
    return days


def test_weekly_summary_reports_the_week_and_respects_preferred_range(tmp_path):
    root = make_repo(tmp_path, rich_week(tmp_path))
    profile = load_profile(root)
    sub = SubmissionGenerator(root, profile).generate(week=1)
    summary = sub.weekly_summary
    assert count_chars(summary) <= profile.weekly_summary_char_limit
    assert count_chars(summary) == sub.summary_count
    # The summary is about the week, not a re-listing of each day.
    assert "40 hours" in summary
    assert "O'Care" in summary or "O'Zone" in summary
    assert sub.summary_band in {"Concise", "Detailed"}
    assert count_chars(summary) >= 350
    check = next(c for c in sub.checks if c.name == "Weekly summary")
    assert check.status == PASS


def test_supplied_summary_over_limit_is_shortened_before_validation(tmp_path):
    root = make_repo(tmp_path, five_day_week(tmp_path))
    profile = load_profile(root)
    long_summary = " ".join(
        f"Day {i} covered structured regression testing of the O'Care production build "
        f"and recorded the outcomes in the defect tracker." for i in range(120)
    )
    assert count_chars(long_summary) > 4000
    sub = SubmissionGenerator(root, profile).generate(week=1, summary_text=long_summary)
    assert sub.summary_count <= profile.weekly_summary_char_limit
    assert sub.summary_count == count_chars(sub.weekly_summary)
    assert next(c for c in sub.checks if c.name == "Weekly summary").status == PASS


def test_exactly_one_attachment_is_recommended(tmp_path):
    days = five_day_week(
        tmp_path,
        overrides={
            0: {
                "attachments": "1. `attachments/week-01/regression-report.pdf`\n"
                "2. `attachments/week-01/defect-list.md`"
            }
        },
    )
    root = make_repo(tmp_path, days)
    week_dir = root / "attachments" / "week-01"
    week_dir.mkdir(parents=True)
    (week_dir / "regression-report.pdf").write_bytes(b"%PDF-1.4 test")
    (week_dir / "defect-list.md").write_text("# defects\n", encoding="utf-8")
    sub = SubmissionGenerator(root, load_profile(root)).generate(week=1)
    assert sub.attachment.status == "Ready"
    assert sub.attachment.local_path
    assert sub.attachment.consolidation_note  # more than one local file exists
    assert next(c for c in sub.checks if c.name == "Single attachment").status == PASS


def test_referenced_but_absent_attachment_needs_preparation(tmp_path):
    root = make_repo(tmp_path, five_day_week(tmp_path))
    (root / "weeks" / "week-01.md").write_text(
        "# Week 1\n\n# Weekly Summary\n\nDraft.\n\n# Suggested Attachments\n\n"
        "1. Screenshot of the school-filter defect list.\n",
        encoding="utf-8",
    )
    sub = SubmissionGenerator(root, load_profile(root)).generate(week=1)
    assert sub.attachment.status == "Needs Preparation"
    assert "prepare" in sub.attachment.reason.lower()
    assert next(c for c in sub.checks if c.name == "Single attachment").status == ATTENTION


def test_no_attachment_at_all_is_flagged(tmp_path):
    days = five_day_week(tmp_path)
    root = make_repo(tmp_path, days)
    sub = SubmissionGenerator(root, load_profile(root)).generate(week=1)
    # No evidence files, no attachments section -> explicit Missing status.
    assert sub.attachment.status == "Missing"


def test_rendered_output_has_the_required_sections_and_counters(tmp_path):
    root = make_repo(tmp_path, five_day_week(tmp_path))
    sub = SubmissionGenerator(root, load_profile(root)).generate(week=1)
    text = render_submission(sub)
    assert "UNIVERSITY INTERNSHIP SUBMISSION — WEEK 01" in text
    assert text.count("TASK DETAILS:") == 5
    assert "DAY 1 — MONDAY" in text and "DAY 5 — FRIDAY" in text
    assert "Character Count:" in text
    assert "WEEKLY SUMMARY" in text and "WEEKLY ATTACHMENT" in text
    assert "END OF COPY-READY CONTENT" in text
    assert "WARNINGS AND VALIDATION" in text
    # warnings and counters must come after the copy-ready fields
    assert text.index("WARNINGS AND VALIDATION") > text.index("WEEKLY ATTACHMENT")
    for name in (
        "Dates",
        "Daily task details",
        "Character limits",
        "Total hours",
        "Weekly summary",
        "Single attachment",
        "Source accuracy",
    ):
        assert f"- {name}:" in text
    # counters and headings must not leak into the field text
    for day in sub.dailies:
        assert "Character Count" not in day.task_text
        assert "TASK DETAILS" not in day.task_text
    assert "Character Count" not in sub.weekly_summary


def test_orphan_headings_are_removed_after_condensation():
    from submission_generator import drop_orphan_headings

    text = (
        "Intro paragraph with real content.\n\n"
        "C. Consolidated issue list from the app run\n\n"
        "D. Tracker state at close of day\n\n"
        "1. Findings grouped by area — the list breaks down as:\n\n"
        "2. Another section lead-in\n\n"
        "3. Real item with BUG-12 and a measured result."
    )
    cleaned = drop_orphan_headings(text)
    # headings with nothing under them are gone
    assert "C. Consolidated issue list" not in cleaned
    assert "D. Tracker state" not in cleaned
    assert "1. Findings grouped by area" not in cleaned
    # content, and a heading that actually introduces content, survive
    assert "Intro paragraph" in cleaned
    assert "2. Another section lead-in" in cleaned
    assert "3. Real item with BUG-12" in cleaned


def test_plain_text_conversion_strips_markdown():
    md = "### A. Tracker review\n\n1. **BUG-70 (Medium)** — `Status = Not started`\n2. See [page](https://example.com/x)"
    out = to_plain_text(md)
    assert "#" not in out
    assert "**" not in out
    assert "`" not in out
    assert "BUG-70 (Medium)" in out
    assert "page (https://example.com/x)" in out


def test_identical_daily_fields_are_flagged(tmp_path):
    same = "Conducted functional testing of the school filter and recorded the results."
    days = five_day_week(tmp_path, overrides={i: {"task": same} for i in range(5)})
    root = make_repo(tmp_path, days)
    sub = SubmissionGenerator(root, load_profile(root)).generate(week=1)
    check = next(c for c in sub.checks if c.name == "Daily task details")
    assert check.status == ATTENTION
    assert "identical" in check.detail


def test_summary_copying_a_daily_sentence_is_flagged(tmp_path):
    root = make_repo(tmp_path, five_day_week(tmp_path))
    gen = SubmissionGenerator(root, load_profile(root))
    base = gen.generate(week=1)
    copied = base.dailies[0].task_text
    sub = gen.generate(week=1, summary_text=copied)
    check = next(c for c in sub.checks if c.name == "Weekly summary")
    assert check.status == ATTENTION
    assert "copied" in check.detail


def test_source_accuracy_detects_unrecorded_identifiers(tmp_path):
    root = make_repo(tmp_path, five_day_week(tmp_path))
    gen = SubmissionGenerator(root, load_profile(root))
    base = gen.generate(week=1)
    summary = base.weekly_summary + " Additional fix verified in BUG-999."
    sub = gen.generate(week=1, summary_text=summary)
    check = next(c for c in sub.checks if c.name == "Source accuracy")
    assert check.status == ATTENTION
    assert "BUG-999" in check.detail


def test_authored_daily_override_is_used_and_measured(tmp_path):
    root = make_repo(tmp_path, five_day_week(tmp_path))
    gen = SubmissionGenerator(root, load_profile(root))
    authored = "Reviewed the defect tracker and confirmed BUG-11 was reproducible on staging."
    sub = gen.generate(week=1, daily_overrides={date(2026, 8, 3): authored})
    day = sub.dailies[0]
    assert day.task_text == authored
    assert day.count == count_chars(authored)
    assert day.authored is True
    # Authored text still has to be traceable; unrelated wording is flagged.
    check = next(c for c in sub.checks if c.name == "Source accuracy")
    assert check.status == ATTENTION
    assert "2026-08-03" in check.detail


def test_daily_only_generation(tmp_path):
    root = make_repo(tmp_path, five_day_week(tmp_path))
    gen = SubmissionGenerator(root, load_profile(root))
    day = gen.generate_day(date(2026, 8, 5))
    assert day.weekday == "Wednesday"
    assert day.count == count_chars(day.task_text)
    assert check_limit(day.task_text).within_limit


def test_generate_day_for_missing_date_raises(tmp_path):
    root = make_repo(tmp_path, five_day_week(tmp_path))
    gen = SubmissionGenerator(root, load_profile(root))
    with pytest.raises(FileNotFoundError):
        gen.generate_day(date(2026, 8, 20))


def test_generate_day_honours_authored_override(tmp_path):
    root = make_repo(tmp_path, five_day_week(tmp_path))
    gen = SubmissionGenerator(root, load_profile(root))
    authored = "Executed the assigned checklist items and logged BUG-12 against staging."
    day = gen.generate_day(
        date(2026, 8, 5), daily_overrides={date(2026, 8, 5): authored}
    )
    assert day.task_text == authored
    assert day.count == count_chars(authored)
    assert day.authored is True


def test_generate_day_ignores_override_for_another_date(tmp_path):
    root = make_repo(tmp_path, five_day_week(tmp_path))
    gen = SubmissionGenerator(root, load_profile(root))
    authored = "Executed the assigned checklist items and logged BUG-12 against staging."
    day = gen.generate_day(
        date(2026, 8, 5), daily_overrides={date(2026, 8, 4): authored}
    )
    assert day.task_text != authored
    assert day.authored is False


def test_condense_keeps_source_claims_only(tmp_path):
    task = "Tested the SOS alert toggle on the settings page and confirmed it persisted."
    root = make_repo(tmp_path, {START: daily_md(START.isoformat(), "Monday", task)})
    profile = load_profile(root)
    record = LogbookReader(root, profile).read_daily(START)
    text, fit = compose_daily_task(record, limit=profile.daily_task_char_limit)
    assert "SOS alert toggle" in text
    assert fit.final_count == count_chars(text)
    assert "deployed" not in text.lower()


# ---------------------------------------------------------------------------
# Concise output (preferred length), noise removal, honesty
# ---------------------------------------------------------------------------

LONG_DAY = """Reviewed the O'Zone staging build and executed the scheduled regression checks.
The run covered login, upload, watch and settings flows on desktop and mobile viewports.
A timestamped log was written at 14:32:07 to attachments/week-01/run-log-2026-08-03.md.
Full details are available at https://tracker.example.com/tests?run=4481 for reference.
Forty cases were executed and twelve passed, with two failures reported as BUG-501 and BUG-502.
Seven partial results were recorded for cases that could not complete without a second account.
Five cases were blocked by missing admin credentials and four were skipped by design.
The remaining twelve cases were not run because the refreshed staging URL was not issued.
The upload flow rejected MOV files above 200 MB, which reproduced twice and was logged as BUG-503.
Subtitle handling kept only one file when several were selected, already known as BUG-504.
A short note was added to the tracker for each case, listing the observed behaviour.
The session closed with the regression board updated and the blockers passed to the supervisor.
"""


def test_daily_field_is_concise_and_measured(tmp_path):
    root = make_repo(tmp_path, {START: daily_md(START.isoformat(), "Monday", LONG_DAY)})
    profile = load_profile(root)
    day = SubmissionGenerator(root, profile).generate(week=1).dailies[0]
    assert day.count == count_chars(day.task_text)
    assert day.count <= profile.daily_task_preferred_max
    assert day.band == "Concise"
    # 4,000 is a ceiling, not a target: the field is nowhere near it.
    assert day.count < profile.daily_task_char_limit / 2


def test_daily_field_drops_administrative_noise(tmp_path):
    root = make_repo(tmp_path, {START: daily_md(START.isoformat(), "Monday", LONG_DAY)})
    text = SubmissionGenerator(root, load_profile(root)).generate(week=1).dailies[0].task_text
    assert "https://" not in text
    assert "14:32:07" not in text
    assert "attachments/week-01" not in text


def test_daily_field_keeps_findings_and_defects(tmp_path):
    root = make_repo(tmp_path, {START: daily_md(START.isoformat(), "Monday", LONG_DAY)})
    text = SubmissionGenerator(root, load_profile(root)).generate(week=1).dailies[0].task_text
    assert "BUG-501" in text or "BUG-502" in text or "BUG-503" in text
    assert "blocked" in text.lower() or "skipped" in text.lower()


def test_busy_day_may_exceed_preferred_but_never_the_limit(tmp_path):
    days = rich_week(tmp_path)
    root = make_repo(tmp_path, days)
    profile = load_profile(root)
    sub = SubmissionGenerator(root, profile).generate(week=1)
    for day in sub.dailies:
        assert day.count <= profile.daily_task_char_limit
        assert day.band in {"Concise", "Detailed"}


def test_weekly_summary_does_not_repeat_daily_sentences(tmp_path):
    root = make_repo(tmp_path, rich_week(tmp_path))
    sub = SubmissionGenerator(root, load_profile(root)).generate(week=1)
    daily_sentences = {
        " ".join(s.lower().split())
        for d in sub.dailies
        for s in d.task_text.split(". ")
        if len(s) > 40
    }
    weekly_sentences = [s for s in sub.weekly_summary.split(". ") if len(s) > 40]
    repeated = [s for s in weekly_sentences if " ".join(s.lower().split()) in daily_sentences]
    assert repeated == []
    check = next(c for c in sub.checks if c.name == "Weekly summary")
    assert "copied" not in check.detail


def test_week_report_summary_is_used_and_trimmed(tmp_path):
    days = rich_week(tmp_path)
    root = make_repo(tmp_path, days)
    (root / "weeks" / "week-01.md").write_text(
        "# Week 1\n\n# Weekly Summary\n\n"
        + "The week was spent on O'Zone regression work. " * 40
        + "\n\n# Suggested Attachments\n\n1. Test run report.\n",
        encoding="utf-8",
    )
    profile = load_profile(root)
    sub = SubmissionGenerator(root, profile).generate(week=1)
    assert count_chars(sub.weekly_summary) <= profile.weekly_summary_preferred_max
    assert "O'Zone" in sub.weekly_summary


def test_incorrect_defect_total_in_week_report_is_corrected(tmp_path):
    days = rich_week(tmp_path)  # BUG-200..BUG-204 in the records
    root = make_repo(tmp_path, days)
    (root / "weeks" / "week-01.md").write_text(
        "# Week 1\n\n# Weekly Summary\n\n"
        "Two defects were reported during the week and most checks passed. "
        "The regression pass covered the school filter, the upload module and "
        "the invitation flow across five working days on the staging build.\n\n"
        "The remaining work was carried into the next week after the supervisor "
        "reviewed the open blockers and agreed the order of the follow-up checks.\n",
        encoding="utf-8",
    )
    sub = SubmissionGenerator(root, load_profile(root)).generate(week=1)
    assert "Two defects were reported" not in sub.weekly_summary
    assert "5 defects were recorded" in sub.weekly_summary
    assert any("daily records contain 5" in note for note in sub.notes)


def test_length_band_is_shown_outside_the_field(tmp_path):
    root = make_repo(tmp_path, rich_week(tmp_path))
    profile = load_profile(root)
    sub = SubmissionGenerator(root, profile).generate(week=1)
    rendered = render_submission(sub)
    assert f"({sub.dailies[0].band})" in rendered
    assert f"({sub.summary_band})" in rendered
    for day in sub.dailies:
        assert "Concise" not in day.task_text
        assert "Detailed" not in day.task_text
