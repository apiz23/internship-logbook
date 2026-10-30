"""Tests for reading existing logbook files (backward compatibility)."""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from logbook_reader import LogbookReader, parse_sections, parse_top_sections  # noqa: E402
from university_profile import UniversitySubmissionProfile  # noqa: E402


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_parse_sections_keeps_body_verbatim(tmp_path):
    path = write(
        tmp_path / "daily" / "2026-08-03.md",
        "# 2026-08-03 (Monday)\n\n## Task Detail\n\nTested the filter.\n\n"
        "## Total Hours\n\n8 hours\n",
    )
    sections = parse_sections(path.read_text())
    assert sections["task detail"] == "Tested the filter."
    assert sections["total hours"] == "8 hours"


def test_parse_top_sections_splits_weekly_report(tmp_path):
    text = (
        "# Week 12\n\n## Monday (Oct 19)\n\n### Task Detail\n\nDid work.\n\n"
        "# Weekly Summary\n\nThe week moved.\n\n# Suggested Attachments\n\n1. Evidence.\n"
    )
    tops = parse_top_sections(text)
    assert tops["weekly summary"] == "The week moved."
    assert "Evidence" in tops["suggested attachments"]


def test_reader_handles_legacy_day_headings(tmp_path):
    profile = UniversitySubmissionProfile(internship_start_date=date(2026, 8, 3))
    write(
        tmp_path / "weeks" / "week-12.md",
        "# Week 12\n\n## Monday (Oct 19)\n\n### Task Detail\n\nWork.\n\n"
        "# Weekly Summary\n\nSummary text.\n",
    )
    weekly = LogbookReader(tmp_path, profile).read_weekly(12)
    assert "monday (oct 19)" in weekly.days
    assert weekly.summary == "Summary text."


def test_reader_does_not_treat_executing_as_a_holiday(tmp_path):
    """Regression: the substring 'cuti' inside 'executing' is not a holiday."""
    profile = UniversitySubmissionProfile(internship_start_date=date(2026, 8, 3))
    write(
        tmp_path / "daily" / "2026-08-04.md",
        "# 2026-08-04 (Tuesday)\n\n## Task Detail\n\nExecuting the regression suite.\n\n"
        "## Total Hours\n\n8 hours\n",
    )
    record = LogbookReader(tmp_path, profile).read_daily(date(2026, 8, 4))
    assert record.is_holiday is False


def test_reader_flags_holiday_records(tmp_path):
    profile = UniversitySubmissionProfile(internship_start_date=date(2026, 8, 3))
    write(
        tmp_path / "daily" / "2026-08-31.md",
        "# 2026-08-31 (Monday)\n\n## Raw Notes\n\n- Public Holiday — Merdeka Day. No work / Cuti.\n\n"
        "## Total Hours\n\n0 hours\n",
    )
    record = LogbookReader(tmp_path, profile).read_daily(date(2026, 8, 31))
    assert record.is_holiday is True


def test_available_weeks_counts_from_start(tmp_path):
    profile = UniversitySubmissionProfile(internship_start_date=date(2026, 8, 3))
    write(tmp_path / "daily" / "2026-08-03.md", "# 2026-08-03 (Monday)\n")
    write(tmp_path / "daily" / "2026-08-14.md", "# 2026-08-14 (Friday)\n")
    reader = LogbookReader(tmp_path, profile)
    assert reader.available_weeks() == [1, 2]


def test_missing_day_reported_with_reason(tmp_path):
    profile = UniversitySubmissionProfile(internship_start_date=date(2026, 8, 3))
    write(
        tmp_path / "daily" / "2026-08-03.md",
        "# 2026-08-03 (Monday)\n\n## Task Detail\n\nWork.\n\n## Total Hours\n\n8 hours\n",
    )
    collection = LogbookReader(tmp_path, profile).collect_week(1)
    assert [m.day.isoformat() for m in collection.missing] == [
        "2026-08-04",
        "2026-08-05",
        "2026-08-06",
        "2026-08-07",
    ]
    assert all("no daily record" in m.reason for m in collection.missing)


def test_profile_defaults_match_the_generic_skill(tmp_path):
    profile = UniversitySubmissionProfile()
    assert profile.daily_task_char_limit == 4000
    assert profile.weekly_summary_char_limit == 4000
    assert profile.max_weekly_attachments == 1
    assert profile.working_days == [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
    ]
    assert profile.daily_fields == ["date", "task_details", "total_hours"]
    assert profile.weekly_fields == ["weekly_summary", "attachment"]


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "daily").is_dir(),
    reason="no local logbook data",
)
def test_real_repository_reads_without_error():
    """The user's real logbook must still parse after this change."""
    root = Path(__file__).resolve().parents[1]
    profile = UniversitySubmissionProfile(internship_start_date=date(2026, 8, 3))
    reader = LogbookReader(root, profile)
    weeks = reader.available_weeks()
    assert weeks, "expected daily records in the repository"
    for week in weeks[-3:]:
        collection = reader.collect_week(week)
        assert collection.records or collection.missing
        for record in collection.records:
            assert record.day.isoformat() == record.path.stem
