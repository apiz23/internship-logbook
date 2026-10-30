"""Read the existing logbook files into structured records.

The university submission generator must not invent a second source of
truth. This reader parses the files the logbook already produces -
``daily/YYYY-MM-DD.md`` and ``weeks/week-XX.md`` - and exposes them as
records the generator and validator can use. It reads only; nothing here
writes to the logbook.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from university_profile import UniversitySubmissionProfile, WEEKDAY_NAMES

DAILY_DIR = "daily"
WEEKS_DIR = "weeks"
PROJECTS_DIR = "projects"

_H1 = re.compile(r"^#\s+(.+?)\s*$", re.M)
_H2 = re.compile(r"^##\s+(.+?)\s*$", re.M)
_SECTION_SPLIT = re.compile(r"^##\s+(.+?)\s*$", re.M)
_TOP_SPLIT = re.compile(r"^#\s+(.+?)\s*$", re.M)
_HOURS_NUMBER = re.compile(r"(\d+(?:\.\d+)?)")
_ISO_IN_HEADING = re.compile(r"(\d{4}-\d{2}-\d{2})")
_BUG_ID = re.compile(r"\bBUG-\d+\b")
_TEST_ID = re.compile(r"\bTC-?\d+\b")
_URL = re.compile(r"https?://\S+")


class LogbookError(RuntimeError):
    pass


def parse_hours(text: str) -> Optional[float]:
    """Parse a Total Hours section value, or ``None`` when it is not a number.

    ``TBC``, a bare dash, or a placeholder sentence all mean "unknown" -
    never treat them as zero and never carry a neighbouring value across.
    """
    if not text:
        return None
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if not first:
        return None
    lowered = first.lower()
    if any(token in lowered for token in ("tbc", "tba", "n/a", "not stated", "unknown")):
        return None
    match = _HOURS_NUMBER.search(first)
    if not match:
        return None
    value = float(match.group(1))
    return value if value > 0 else 0.0


def format_hours(value: Optional[float]) -> str:
    """Format hours for display: ``8 hours``, ``7.5 hours``, or a placeholder."""
    if value is None:
        return "NOT RECORDED"
    return f"{int(value) if value == int(value) else value} hours"


def parse_sections(markdown: str) -> dict[str, str]:
    """Return ``## heading`` sections as ``{lowercased heading: body}``."""
    sections: dict[str, str] = {}
    matches = list(_SECTION_SPLIT.finditer(markdown))
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        sections[match.group(1).strip().lower()] = markdown[start:end].strip()
    return sections


def parse_top_sections(markdown: str) -> dict[str, str]:
    """Return ``# heading`` sections as ``{lowercased heading: body}``."""
    sections: dict[str, str] = {}
    matches = list(_TOP_SPLIT.finditer(markdown))
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        sections[match.group(1).strip().lower()] = markdown[start:end].strip()
    return sections


@dataclass
class DailyRecord:
    """One ``daily/YYYY-MM-DD.md`` file, parsed."""

    day: date
    path: Path
    raw_notes: str = ""
    task_detail: str = ""
    issue: str = ""
    proposed_solution: str = ""
    status: str = ""
    total_hours_text: str = ""
    total_hours: Optional[float] = None
    attachments: str = ""
    extra_sections: dict[str, str] = field(default_factory=dict)

    @property
    def weekday(self) -> str:
        return WEEKDAY_NAMES[self.day.weekday()]

    @property
    def is_holiday(self) -> bool:
        """True only when the record says it was a non-working holiday.

        Matched on word boundaries: "executing" contains the letters of
        "cuti" but is not a holiday marker.
        """
        haystack = f"{self.raw_notes}\n{self.task_detail}\n{self.status}".lower()
        if "public holiday" in haystack or re.search(r"\bcuti\b", haystack):
            return True
        return self.total_hours == 0 and not self.task_detail.strip()

    @property
    def hours_recorded(self) -> bool:
        return self.total_hours is not None

    @property
    def bug_ids(self) -> list[str]:
        return sorted(set(_BUG_ID.findall(self.task_detail + "\n" + self.issue)))

    @property
    def test_ids(self) -> list[str]:
        return sorted(set(_TEST_ID.findall(self.task_detail + "\n" + self.issue)))

    def combined_text(self) -> str:
        return "\n\n".join(
            part
            for part in (
                self.task_detail,
                self.issue,
                self.proposed_solution,
                self.status,
            )
            if part.strip()
        )


@dataclass
class WeeklyReport:
    """One ``weeks/week-XX.md`` file, parsed."""

    number: int
    path: Path
    days: dict[str, str] = field(default_factory=dict)  # lowercased day heading -> body
    summary: str = ""
    suggested_attachments: str = ""


@dataclass
class MissingDay:
    day: date
    weekday: str
    reason: str


@dataclass
class WeekCollection:
    """Everything the generator needs for one internship week."""

    number: int
    start: date
    end: date
    expected_days: list[date]
    holidays: dict[str, str]
    records: list[DailyRecord]
    missing: list[MissingDay]
    weekly: Optional[WeeklyReport] = None

    @property
    def present_days(self) -> list[date]:
        return [r.day for r in self.records if not r.is_holiday]

    @property
    def total_hours(self) -> Optional[float]:
        values = [r.total_hours for r in self.records if r.total_hours is not None]
        return sum(values) if values else None

    @property
    def days_missing_hours(self) -> list[DailyRecord]:
        return [r for r in self.records if not r.hours_recorded and not r.is_holiday]


class LogbookReader:
    """Read-only access to a logbook repository."""

    def __init__(self, root: str | Path, profile: UniversitySubmissionProfile):
        self.root = Path(root).resolve()
        self.profile = profile
        if profile.internship_start_date is None:
            raise LogbookError(
                "internship_start_date is required to compute internship weeks"
            )
        self.start = profile.internship_start_date

    # -- week maths -------------------------------------------------------
    def week_number_for(self, day: date) -> int:
        """Week number for ``day``, anchored on the internship start date.

        Weeks are 7 calendar days long starting at the configured start
        date; the working-day set decides which days inside a week are
        expected, not where the week begins.
        """
        delta = (day - self.start).days
        if delta < 0:
            raise LogbookError(
                f"{day.isoformat()} is before the internship start "
                f"({self.start.isoformat()})"
            )
        return delta // 7 + 1

    def week_start(self, number: int) -> date:
        if number < 1:
            raise LogbookError("Week numbers start at 1")
        return self.start + timedelta(days=7 * (number - 1))

    def week_end(self, number: int) -> date:
        return self.week_start(number) + timedelta(days=6)

    def expected_days(self, number: int) -> list[date]:
        begin = self.week_start(number)
        weekdays = self.profile.working_weekdays
        days = [
            begin + timedelta(days=i)
            for i in range(7)
            if (begin + timedelta(days=i)).weekday() in weekdays
        ]
        return days

    def current_week(self, today: Optional[date] = None) -> int:
        return self.week_number_for(today or date.today())

    # -- file access ------------------------------------------------------
    def daily_path(self, day: date) -> Path:
        return self.root / DAILY_DIR / f"{day.isoformat()}.md"

    def weekly_path(self, number: int) -> Path:
        return self.root / WEEKS_DIR / f"week-{number:02d}.md"

    def read_daily(self, day: date) -> Optional[DailyRecord]:
        path = self.daily_path(day)
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8")
        sections = parse_sections(text)
        known = {
            "raw notes",
            "task detail",
            "issue",
            "proposed solution",
            "status",
            "total hours",
            "attachments",
        }
        hours_text = sections.get("total hours", "")
        return DailyRecord(
            day=day,
            path=path,
            raw_notes=sections.get("raw notes", ""),
            task_detail=sections.get("task detail", ""),
            issue=sections.get("issue", ""),
            proposed_solution=sections.get("proposed solution", ""),
            status=sections.get("status", ""),
            total_hours_text=hours_text,
            total_hours=parse_hours(hours_text),
            attachments=sections.get("attachments", ""),
            extra_sections={k: v for k, v in sections.items() if k not in known},
        )

    def read_weekly(self, number: int) -> Optional[WeeklyReport]:
        path = self.weekly_path(number)
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8")
        tops = parse_top_sections(text)
        day_sections: dict[str, str] = {}
        for heading, body in parse_sections(text).items():
            if heading in {"weekly summary", "suggested attachments"}:
                continue
            day_sections[heading] = body
        return WeeklyReport(
            number=number,
            path=path,
            days=day_sections,
            summary=tops.get("weekly summary", ""),
            suggested_attachments=tops.get("suggested attachments", ""),
        )

    # -- collection -------------------------------------------------------
    def collect_week(self, number: int) -> WeekCollection:
        start, end = self.week_start(number), self.week_end(number)
        holidays: dict[str, str] = {}
        records: list[DailyRecord] = []
        missing: list[MissingDay] = []

        for day in self.expected_days(number):
            holiday_name = self.profile.holiday(day)
            record = self.read_daily(day)
            if record is not None and record.is_holiday:
                holidays[day.isoformat()] = holiday_name or "Public holiday"
                records.append(record)
                continue
            if holiday_name:
                holidays[day.isoformat()] = holiday_name
            if record is None:
                missing.append(
                    MissingDay(
                        day=day,
                        weekday=WEEKDAY_NAMES[day.weekday()],
                        reason=(
                            f"public holiday ({holiday_name}) but no daily file"
                            if holiday_name
                            else "no daily record for this working day"
                        ),
                    )
                )
                continue
            records.append(record)

        return WeekCollection(
            number=number,
            start=start,
            end=end,
            expected_days=self.expected_days(number),
            holidays=holidays,
            records=records,
            missing=missing,
            weekly=self.read_weekly(number),
        )

    def available_weeks(self) -> list[int]:
        if not (self.root / DAILY_DIR).is_dir():
            return []
        weeks = set()
        for path in sorted((self.root / DAILY_DIR).glob("*.md")):
            try:
                day = date.fromisoformat(path.stem)
            except ValueError:
                continue
            try:
                weeks.add(self.week_number_for(day))
            except LogbookError:
                continue
        return sorted(weeks)

    def project_names(self) -> list[str]:
        folder = self.root / PROJECTS_DIR
        if not folder.is_dir():
            return []
        return sorted(p.stem for p in folder.glob("*.md"))
