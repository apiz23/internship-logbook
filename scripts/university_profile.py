"""University submission profile: limits, working days, timeline.

The generic skill must not hardcode one university's rules. Everything
specific to a submission portal lives in a JSON profile (local, not
committed) or in the user's own ``AGENTS.md``. This module loads that
profile with sane generic defaults, so the feature works out of the box and
can be re-pointed at another university without editing code.

Load order (first hit wins):
    1. ``$UNIVERSITY_SUBMISSION_CONFIG``
    2. ``<repo>/config/university-submission.json``
    3. defaults in this module, plus ``internship_start_date`` scraped
       from ``<repo>/AGENTS.md`` when the profile omits it.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

DEFAULT_CONFIG_RELPATH = Path("config") / "university-submission.json"

WEEKDAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

SUPPORTED_DAILY_FIELDS = ("date", "task_details", "total_hours")
SUPPORTED_WEEKLY_FIELDS = ("weekly_summary", "attachment")


class ProfileError(RuntimeError):
    """Raised when the submission profile cannot be used as configured."""


def _parse_iso_date(value: str) -> Optional[date]:
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None


def weekday_numbers(names: list[str]) -> list[int]:
    """Map weekday names to ``date.weekday()`` numbers, keeping order."""
    out = []
    for name in names:
        key = name.strip().capitalize()[:3]
        for i, full in enumerate(WEEKDAY_NAMES):
            if full[:3] == key:
                out.append(i)
                break
        else:
            raise ProfileError(f"Unknown weekday name in working_days: {name!r}")
    return sorted(set(out))


_START_LINE = re.compile(
    r"(?im)^[^\n]*\b(?:start(?:ing)?(?:\s+date)?|commenc\w*|first\s+day|timeline)\b[^\n]*$"
)
_ISO = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def parse_start_date_from_agents_md(text: str) -> Optional[date]:
    """Find the internship start date in free-form ``AGENTS.md`` text.

    Looks only at lines that name a start/commencement/timeline, and only
    accepts an explicit ISO date on that line. Returns ``None`` rather than
    guessing from other dates in the file.
    """
    for match in _START_LINE.finditer(text or ""):
        line = match.group(0)
        iso = _ISO.search(line)
        if iso:
            return _parse_iso_date(iso.group(1))
    return None


@dataclass
class UniversitySubmissionProfile:
    """Portal rules for the university submission generator."""

    profile_name: str = "University internship submission"
    submission_enabled: bool = True
    daily_task_char_limit: int = 4000
    weekly_summary_char_limit: int = 4000
    target_min_chars: int = 3500
    target_max_chars: int = 3800
    working_days: list[str] = field(
        default_factory=lambda: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    )
    daily_fields: list[str] = field(
        default_factory=lambda: list(SUPPORTED_DAILY_FIELDS)
    )
    weekly_fields: list[str] = field(
        default_factory=lambda: list(SUPPORTED_WEEKLY_FIELDS)
    )
    max_weekly_attachments: int = 1
    output_language: str = "en"
    internship_start_date: Optional[date] = None
    default_hours: Optional[float] = None
    public_holidays: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    # -- helpers ----------------------------------------------------------
    @property
    def working_weekdays(self) -> list[int]:
        return weekday_numbers(self.working_days)

    def holiday(self, day: date) -> Optional[str]:
        return self.public_holidays.get(day.isoformat())

    def validate(self) -> None:
        if self.daily_task_char_limit <= 0 or self.weekly_summary_char_limit <= 0:
            raise ProfileError("Character limits must be positive")
        if self.target_min_chars > self.target_max_chars:
            raise ProfileError("target_min_chars must not exceed target_max_chars")
        if self.target_max_chars > self.weekly_summary_char_limit:
            raise ProfileError("target_max_chars must not exceed the weekly limit")
        if self.max_weekly_attachments != 1:
            raise ProfileError(
                "This portal accepts exactly one attachment per weekly submission; "
                "set max_weekly_attachments to 1"
            )
        unknown = [f for f in self.daily_fields if f not in SUPPORTED_DAILY_FIELDS]
        if unknown:
            raise ProfileError(f"Unsupported daily field(s): {unknown}")
        unknown = [f for f in self.weekly_fields if f not in SUPPORTED_WEEKLY_FIELDS]
        if unknown:
            raise ProfileError(f"Unsupported weekly field(s): {unknown}")
        if not self.working_weekdays:
            raise ProfileError("At least one working day is required")
        if self.internship_start_date is None:
            raise ProfileError(
                "No internship start date configured. Add 'internship_start_date' to "
                "config/university-submission.json or an 'Internship start date: "
                "YYYY-MM-DD' line to AGENTS.md."
            )


def _profile_from_dict(data: dict) -> UniversitySubmissionProfile:
    start = data.get("internship_start_date") or data.get("start_date")
    parsed = _parse_iso_date(start) if start else None
    holidays = data.get("public_holidays") or {}
    if not isinstance(holidays, dict):
        raise ProfileError("public_holidays must be an object of ISO date -> name")

    profile = UniversitySubmissionProfile(
        profile_name=data.get("profile_name", "University internship submission"),
        submission_enabled=bool(data.get("submission_enabled", True)),
        daily_task_char_limit=int(data.get("daily_task_char_limit", 4000)),
        weekly_summary_char_limit=int(data.get("weekly_summary_char_limit", 4000)),
        target_min_chars=int(data.get("target_min_chars", 3500)),
        target_max_chars=int(data.get("target_max_chars", 3800)),
        working_days=list(
            data.get(
                "working_days",
                ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
            )
        ),
        daily_fields=list(data.get("daily_fields", SUPPORTED_DAILY_FIELDS)),
        weekly_fields=list(data.get("weekly_fields", SUPPORTED_WEEKLY_FIELDS)),
        max_weekly_attachments=int(data.get("max_weekly_attachments", 1)),
        output_language=str(data.get("output_language", "en")),
        internship_start_date=parsed,
        default_hours=(
            float(data["default_hours"]) if data.get("default_hours") is not None else None
        ),
        public_holidays={str(k): str(v) for k, v in holidays.items()},
    )
    if start and parsed is None:
        profile.warnings.append(
            f"internship_start_date {start!r} is not an ISO date (YYYY-MM-DD)"
        )
    return profile


def load_profile(root: str | Path = ".", path: str | Path | None = None) -> UniversitySubmissionProfile:
    """Load the submission profile for ``root``.

    Missing config is not an error: you get the generic defaults plus the
    start date from ``AGENTS.md`` when present. A present-but-broken config
    is an error, because silently ignoring it would generate wrong fields.
    """
    root = Path(root).resolve()
    candidates: list[Path] = []
    env_path = os.environ.get("UNIVERSITY_SUBMISSION_CONFIG")
    if env_path:
        candidates.append(Path(env_path).expanduser())
    if path:
        candidates.append(Path(path).expanduser())
    candidates.append(root / DEFAULT_CONFIG_RELPATH)

    data: dict = {}
    for candidate in candidates:
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ProfileError(f"{candidate} is not valid JSON: {exc}") from exc
            break

    profile = _profile_from_dict(data)

    if profile.internship_start_date is None:
        agents_md = root / "AGENTS.md"
        if agents_md.is_file():
            found = parse_start_date_from_agents_md(agents_md.read_text(encoding="utf-8"))
            if found:
                profile.internship_start_date = found
                profile.warnings.append(
                    f"internship_start_date taken from AGENTS.md ({found.isoformat()})"
                )
    return profile
