"""Generate validated university-submission content from the logbook.

Pipeline (all deterministic, all measured):

    daily/*.md + weeks/week-XX.md
        -> LogbookReader      (existing source of truth, read-only)
        -> condense daily     (delete-only condensation, measured)
        -> weekly summary     (drafted from the same records)
        -> exactly one attachment recommendation
        -> validation checks  (counts, dates, hours, duplication, traceability)
        -> render             (copy-ready blocks, counters outside the text)

Nothing in this module invents activity: if a working day has no daily
record, the day is reported as missing and the generator asks for it instead
of filling it in. Nothing is submitted anywhere; the output is text for the
user to paste into their own portal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable, Optional

from char_limit import (
    DEFAULT_LIMIT,
    FitResult,
    check_limit,
    count_chars,
    fit_to_limit,
    normalise_newlines,
)
from logbook_reader import (
    WEEKDAY_NAMES,
    DailyRecord,
    LogbookReader,
    WeekCollection,
    format_hours,
)
from university_profile import UniversitySubmissionProfile

PASS = "PASS"
ATTENTION = "NEEDS ATTENTION"

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_BUG_ID = re.compile(r"\bBUG-\d+\b")
_TEST_ID = re.compile(r"\bTC-?\d+\b")
_WS = re.compile(r"\s+")
_ACTIVITY_KEYWORDS = {
    "testing": ("test", "testing", "regression", "verify", "verification", "case"),
    "debugging": ("bug", "defect", "debug", "reproduce", "error"),
    "documentation": ("document", "documentation", "write-up", "log", "readme"),
    "research": ("research", "review", "compare", "investigate", "analysis"),
    "development": ("implement", "develop", "build", "code", "refactor", "script"),
    "automation": ("automation", "automate", "playwright", "script", "pipeline"),
}
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’.\-/%]*")


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def split_sentences(text: str) -> list[str]:
    flat = _WS.sub(" ", (text or "").replace("\n", " ")).strip()
    if not flat:
        return []
    return [s.strip() for s in _SENTENCE_END.split(flat) if s.strip()]


def first_sentences(text: str, count: int = 1) -> str:
    return " ".join(split_sentences(text)[:count]).strip()


def normalise_for_compare(text: str) -> str:
    return _WS.sub(" ", (text or "").lower()).strip(" .;:-")


def words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text or "") if len(w) > 2}


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if count_chars(text) <= limit:
        return text
    return fit_to_limit(text, limit=limit).text


_MD_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+", re.M)
_MD_EMPHASIS = re.compile(r"(\*\*|__|\*|_)(?=\S)(.+?)(?<=\S)\1")
_MD_CODE = re.compile(r"`([^`]*)`")
_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_ORDERED = re.compile(r"^(\s*)(\d+)[.)]\s+")


def to_plain_text(text: str) -> str:
    """Convert logbook Markdown into text a portal textarea can hold.

    Headings lose their ``#`` markers, emphasis and inline-code markers are
    removed (the words stay), Markdown links become ``label (url)``, and
    ordered lists are renumbered sequentially after any condensation so the
    remaining items do not show gaps. No wording is changed.
    """
    out = normalise_newlines(text or "")
    out = _MD_LINK.sub(lambda m: f"{m.group(1)} ({m.group(2)})", out)
    out = _MD_HEADING.sub("", out)
    out = _MD_CODE.sub(lambda m: m.group(1), out)
    out = _MD_EMPHASIS.sub(lambda m: m.group(2), out)
    # Unbalanced emphasis (bold opening on one line, closing on another)
    out = out.replace("**", "").replace("__", "").replace("`", "")
    out = re.sub(r"\n{3,}", "\n\n", out)

    return out.strip()


_DAY_OPENERS = (
    "today's work was ",
    "today's work continued ",
    "today's work ",
    "today's task was ",
    "the work was ",
    "the day was ",
    "the day began with ",
    "the day started with ",
    "the day continued with ",
    "the day covered ",
    "the day ",
    "work continued on ",
)
_WEEK_ORDINAL = re.compile(
    r"^(?:first|second|third|fourth|fifth|sixth|last)\s+working day of week\s+\d+[.\s\u2014-]*",
    re.I,
)


def renumber_ordered_items(text: str) -> str:
    """Renumber top-level ordered-list items sequentially (no gaps).

    Condensation removes whole items, which leaves 1, 2, 4, 7. Renumbering
    restores a clean sequence without changing the words.
    """
    lines = normalise_newlines(text).split("\n")
    counter = 0
    for i, line in enumerate(lines):
        match = _ORDERED.match(line)
        if match:
            counter += 1
            lines[i] = f"{match.group(1)}{counter}. " + line[match.end():]
        elif line.strip() and not line.startswith((" ", "\t")):
            counter = 0
    return "\n".join(lines)


def _topic_phrase(record: DailyRecord, max_words: int = 16) -> str:
    """Short noun-ish phrase describing a day, for the weekly narrative.

    Takes the first usable sentence of the day's task detail, strips a
    leading filler/ordinal phrase, and caps it. Falls through to later
    sentences when stripping would leave nothing, so a day that opens with
    "Second working day of Week 13." still contributes a topic.
    """
    for sentence in split_sentences(record.task_detail or record.raw_notes)[:3]:
        stem = _MD_EMPHASIS.sub(lambda m: m.group(2), _MD_CODE.sub(lambda m: m.group(1), sentence))
        for prefix in _DAY_OPENERS:
            if stem.lower().startswith(prefix):
                stem = stem[len(prefix):]
                break
        stem = _WEEK_ORDINAL.sub("", stem)
        stem = re.sub(r"https?://\S+", "", stem)
        stem = re.sub(r"\([^)]*\)", "", stem)
        stem = re.sub(r"\s+([,;:.])", r"\1", stem)
        stem = re.sub(r"\(\s*[,;:]?\s*\)", "", stem)
        stem = re.sub(r"\s+", " ", stem).strip(" .;:,—-(")
        if not stem:
            continue
        parts = stem.split()
        if len(parts) > max_words:
            parts = parts[:max_words]
        while parts and parts[-1].lower() in {
            "a", "an", "the", "and", "or", "of", "to", "in", "on", "for",
            "with", "at", "by", "from", "as", "that", "which", "under",
            "was", "were", "is", "are", "plus",
        }:
            parts.pop()
        stem = " ".join(parts).strip(" .;:,—-(")
        if not stem:
            continue
        return _lower_first(stem) if stem[:1].isupper() else stem
    return ""


_STATUS_CANON = {
    "in progress": "In Progress",
    "completed": "Completed",
    "pending review": "Pending Review",
    "pending merge": "Pending Merge",
    "blocked": "Blocked",
    "on hold": "On Hold",
}


def _status_label(record: DailyRecord) -> str:
    """First line of the Status section, markdown stripped and canonically cased."""
    for line in (record.status or "").splitlines():
        clean = _MD_EMPHASIS.sub(lambda m: m.group(2), line).strip(" -")
        if clean:
            label = " ".join(clean.split()[:4])
            return _STATUS_CANON.get(label.lower(), label)
    return ""


def _issue_themes(record: DailyRecord, max_items: int = 2, max_words: int = 14) -> list[str]:
    """First clause of each issue bullet, as a short theme phrase."""
    themes: list[str] = []
    for raw in (record.issue or "").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "```")):
            continue
        line = re.sub(r"^[-*+]\s+", "", line)
        line = _MD_EMPHASIS.sub(lambda m: m.group(2), _MD_CODE.sub(lambda m: m.group(1), line))
        if not line:
            continue
        clause = re.split(r"(?<=[.;])\s+|;\s+", line)[0]
        clause = re.sub(r"\([^)]*\)", "", clause)
        words = clause.split()
        if len(words) > 8:
            breakable = (" with ", " which ", " that ", " because ", " after ",
                         " before ", " so that ", " while ", " and ")
            positions = [clause.find(b, 0) for b in breakable if clause.find(b, 0) > 0]
            if positions:
                clause = clause[: min(positions)]
                words = clause.split()
        if len(words) > max_words:
            clause = " ".join(words[:max_words])
        clause = re.sub(r"\s+", " ", clause).strip(" .;:,")
        if not clause:
            continue
        clause = clause.replace("**", "").strip()
        clause = _lower_first(clause) if clause[:1].isupper() else clause
        if clause:
            themes.append(clause)
        if len(themes) >= max_items:
            break
    return themes


def _lower_first(text: str) -> str:
    """Lowercase the first letter only when the first token is a normal word.

    Protects identifiers and brand names: ``QA``, ``OTalk``, ``O'Care``,
    ``PLY-15`` and ``TC-479`` keep their casing.
    """
    if not text:
        return text
    token = text.split(" ", 1)[0].rstrip(":,")
    if (
        token.isupper()
        or any(c.isupper() for c in token[1:])
        or any(c.isdigit() for c in token)
    ):
        return text
    return text[0].lower() + text[1:]


def _date_label(day: date) -> str:
    return f"{day.strftime('%b')} {day.day}"


# ---------------------------------------------------------------------------
# Daily submission
# ---------------------------------------------------------------------------


@dataclass
class DailySubmission:
    day: date
    weekday: str
    hours: Optional[float]
    task_text: str
    source_path: str
    fit: FitResult
    issues: list[str] = field(default_factory=list)
    incomplete: bool = False

    @property
    def count(self) -> int:
        return count_chars(self.task_text)

    @property
    def within_limit(self) -> bool:
        return self.count <= self.fit.limit

    @property
    def hours_text(self) -> str:
        return format_hours(self.hours)


def _as_prose(text: str, max_items: int = 2) -> str:
    """Flatten a bulleted section into one or two plain sentences.

    Used when appending the day's issue/action to the task detail: bullet
    markers inside a portal textarea read as leftover formatting, so the
    items become a semicolon-joined sentence instead.
    """
    clean = to_plain_text(text)
    # A wrapped bullet is one item: join continuation lines before splitting,
    # keeping real list boundaries.
    merged = re.sub(r"\n(?![ \t]*(?:[-*+\u2022]|\d+[.)])\s)", " ", clean)
    blocks = re.split(r"\n(?=[ \t]*(?:[-*+\u2022]|\d+[.)])\s)", merged)
    items: list[str] = []
    for block in blocks:
        stripped = block.strip().lstrip("-*+\u2022").strip()
        if not stripped or stripped.startswith("#"):
            continue
        for sentence in split_sentences(stripped):
            sentence = sentence.rstrip(" .;:")
            if sentence:
                items.append(sentence)
    if not items:
        return ""
    chosen = items[:max_items]
    for i in range(1, len(chosen)):
        chosen[i] = _lower_first(chosen[i])
    body = "; ".join(chosen)
    return (body[0].upper() + body[1:] + ".") if body else ""


_HEADING_BLOCK = re.compile(r"^(?:[A-Z][.)]|\d+[.)]|#{1,6}\s)")


def _looks_like_heading(block: str) -> bool:
    """True for a short section lead-in that carries no content itself."""
    text = block.strip()
    if "\n" in text or len(text) > 90:
        return False
    if text.endswith(":"):
        return True
    return bool(_HEADING_BLOCK.match(text)) and not text.endswith((".", "!", "?"))


def drop_orphan_headings(text: str) -> str:
    """Remove section headings whose body was condensed away.

    Condensation can leave "C. Consolidated issue list" or "1. Findings
    grouped by area:" with nothing under it. A heading with no following
    content block reads as a broken record, so it goes too.
    """
    blocks = [b for b in normalise_newlines(text).split("\n\n") if b.strip()]
    changed = True
    while changed:
        changed = False
        kept: list[str] = []
        for i, block in enumerate(blocks):
            is_last = i == len(blocks) - 1
            next_is_heading = (not is_last) and _looks_like_heading(blocks[i + 1])
            if _looks_like_heading(block) and (is_last or next_is_heading):
                changed = True
                continue
            kept.append(block)
        blocks = kept
    return "\n\n".join(blocks)


def compose_daily_task(
    record: DailyRecord,
    limit: int = DEFAULT_LIMIT,
    target: Optional[int] = None,
    include_context: bool = True,
) -> tuple[str, FitResult]:
    """Build one day's task detail from its daily record.

    The source task detail is the base. When budget allows, the day's
    recorded issue and proposed solution are appended so a supervisor sees
    problem, action and outcome - still only content that exists in the
    record. The result is always measured after composition.
    """
    base = record.task_detail.strip() or record.raw_notes.strip()
    if not base:
        return "", fit_to_limit("", limit=limit)

    body = base
    if include_context:
        remaining = limit - count_chars(body)
        for label, section in (
            ("Issue identified", record.issue),
            ("Action taken", record.proposed_solution),
        ):
            sentence = _as_prose(section, 2)
            if not sentence:
                continue
            addition = f"\n\n{label}: {sentence}"
            if count_chars(addition) + 40 > remaining:
                continue
            body = body.rstrip() + addition
            remaining = limit - count_chars(body)

    plain = to_plain_text(body)
    fit = fit_to_limit(plain, limit=limit, target=target)
    # Renumber after condensation: dropping items must not leave 1, 2, 4, 7,
    # and remove headings whose body was dropped with them.
    final_text = renumber_ordered_items(drop_orphan_headings(fit.text))
    if final_text != fit.text:
        fit.text = final_text
        fit.final_count = count_chars(final_text)
        if fit.final_count > limit:
            fit = fit_to_limit(final_text, limit=limit, target=target)
    return fit.text, fit


# ---------------------------------------------------------------------------
# Weekly summary
# ---------------------------------------------------------------------------


def draft_weekly_summary(
    collection: WeekCollection,
    limit: int = DEFAULT_LIMIT,
    target_min: int = 3500,
    target_max: int = 3800,
) -> tuple[str, FitResult, list[str]]:
    """Draft a weekly summary from the week's daily records.

    Every sentence is derived from a record: hours and day count, a per-day
    line phrased so it is not an exact copy of the daily field, the issues
    raised, defect/test identifiers actually present, projects actually
    mentioned, and the activity types the wording supports. Returns the
    text, the fit result, and honesty notes about what could not be stated.
    """
    notes: list[str] = []
    active = [r for r in collection.records if not r.is_holiday]
    if not active:
        return "", fit_to_limit("", limit=limit), ["No working-day records in this week."]

    recorded_hours = [r.total_hours for r in active if r.total_hours is not None]
    totals = sum(recorded_hours) if recorded_hours else None
    if totals is None:
        notes.append("No working hours recorded for any day in this week.")
    elif len(recorded_hours) < len(active):
        notes.append(
            f"Hours recorded on {len(recorded_hours)} of {len(active)} working days."
        )
    if collection.holidays:
        notes.append(
            "Public holiday excluded: "
            + ", ".join(sorted(collection.holidays.values()))
            + "."
        )

    span = (
        f"Week {collection.number} covered {len(active)} working days from "
        f"{_date_label(collection.start)} to {_date_label(collection.end)}"
    )
    if totals is not None and len(recorded_hours) == len(active):
        span += f", totalling {format_hours(totals)} of recorded work."
    elif totals is not None:
        span += (
            f", with {format_hours(totals)} recorded across "
            f"{len(recorded_hours)} of those days."
        )
    else:
        span += "."
    paragraphs = [span]

    day_lines = []
    seen_topics: set[str] = set()
    for record in active:
        topic = _topic_phrase(record)
        if not topic:
            notes.append(f"{record.day.isoformat()} has no task detail to summarise.")
            continue
        status = _status_label(record)
        bug_count = len(record.bug_ids)
        topic_key = " ".join(normalise_for_compare(topic).split()[:5])
        if topic_key and topic_key in seen_topics:
            # Say it carried on rather than printing the same clause twice.
            line = f"{record.weekday} ({_date_label(record.day)}): the same area of work continued"
        else:
            seen_topics.add(topic_key)
            line = f"{record.weekday} ({_date_label(record.day)}): {topic}"
        if bug_count:
            noun = "defect" if bug_count == 1 else "defects"
            line += f", with {bug_count} {noun} recorded"
        if status:
            line += f", closing as {status}"
        day_lines.append(line + ".")
    if day_lines:
        paragraphs.append(" ".join(day_lines))

    themes: list[str] = []
    seen_themes: set[str] = set()
    for record in active:
        for theme in _issue_themes(record, max_items=1):
            key = " ".join(normalise_for_compare(theme).split()[:4])
            if key and key not in seen_themes:
                seen_themes.add(key)
                themes.append(theme)
    if themes:
        joined = "; ".join(themes[:3])
        paragraphs.append(f"Issues and blockers recorded during the week included {joined}.")

    status_counts: dict[str, int] = {}
    for record in active:
        label = _status_label(record).lower()
        if label:
            status_counts[label] = status_counts.get(label, 0) + 1
    if status_counts:
        label, count = max(status_counts.items(), key=lambda kv: kv[1])
        pretty = _STATUS_CANON.get(label, label[0].upper() + label[1:])
        if count == len(active):
            paragraphs.append(f"All {count} working days closed as {pretty}.")
        else:
            paragraphs.append(
                f"{count} of {len(active)} working days closed as {pretty}."
            )

    week_text = "\n\n".join(r.combined_text() for r in active)
    bug_ids = sorted(set(_BUG_ID.findall(week_text)))
    test_ids = sorted(set(_TEST_ID.findall(week_text)))
    evidence = []
    if bug_ids:
        evidence.append(f"{len(bug_ids)} defect identifiers ({', '.join(bug_ids[:8])})")
    if test_ids:
        evidence.append(f"{len(test_ids)} test identifiers ({', '.join(test_ids[:8])})")
    if evidence:
        paragraphs.append("The record names " + " and ".join(evidence) + ".")

    lowered = week_text.lower()
    activities = [
        name
        for name, needles in _ACTIVITY_KEYWORDS.items()
        if any(needle in lowered for needle in needles)
    ]
    if activities:
        if len(activities) > 1:
            listed = ", ".join(activities[:-1]) + " and " + activities[-1]
        else:
            listed = activities[0]
        paragraphs.append(f"The week exercised {listed}.")

    projects = _projects_in(week_text)
    if projects:
        paragraphs.append("Work spanned " + ", ".join(projects) + ".")

    draft = "\n\n".join(p for p in paragraphs if p.strip())
    fit = fit_to_limit(draft, limit=limit, target=target_max)
    if fit.changed:
        notes.append(fit.summary())
    return fit.text, fit, notes


def _projects_in(text: str, names: Iterable[str] | None = None) -> list[str]:
    """Project names mentioned in ``text`` (case-insensitive, word-bounded)."""
    pool = list(names) if names else [
        "O'Care",
        "Ocare",
        "OTalk",
        "OZone",
        "Ozone",
        "Kiwi Import",
        "Hermes",
        "Creator Research",
        "Ochat",
    ]
    found: list[str] = []
    seen: set[str] = set()
    lowered = text.lower()
    for name in pool:
        if re.search(rf"(?<![a-z0-9]){re.escape(name.lower())}(?![a-z0-9])", lowered):
            canonical = (
                name.replace("Ocare", "O'Care")
                .replace("Ozone", "O'Zone")
                .replace("Ochat", "OChat")
            )
            key = canonical.lower().replace("'", "")
            if key not in seen:
                seen.add(key)
                found.append(canonical)
    return found


# ---------------------------------------------------------------------------
# Attachment recommendation
# ---------------------------------------------------------------------------


@dataclass
class AttachmentRecommendation:
    filename: str
    reason: str
    status: str  # Ready | Needs Preparation | Missing
    local_path: Optional[str] = None
    candidates_considered: int = 0
    consolidation_note: str = ""


_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic"}
_DOC_EXT = {".pdf", ".docx", ".doc", ".xlsx", ".csv", ".md", ".txt", ".mp4", ".mov"}


def _week_attachment_files(reader: LogbookReader, week: int) -> list[Path]:
    folder = reader.root / "attachments" / f"week-{week:02d}"
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.rglob("*") if p.is_file() and not p.name.startswith("."))


def recommend_attachment(
    reader: LogbookReader,
    collection: WeekCollection,
    max_attachments: int = 1,
) -> AttachmentRecommendation:
    """Pick exactly one attachment (or say what to prepare)."""
    files = _week_attachment_files(reader, collection.number)
    scored: list[tuple[float, str, str, Optional[str]]] = []

    for path in files:
        ext = path.suffix.lower()
        score = 100.0
        if ext == ".pdf":
            score += 30
        elif ext in _IMAGE_EXT:
            score += 25
        elif ext in _DOC_EXT:
            score += 15
        name = path.name.lower()
        for hint, bonus in (
            ("report", 12),
            ("summary", 8),
            ("issue", 8),
            ("bug", 6),
            ("list", 6),
            ("screenshot", 4),
        ):
            if hint in name:
                score += bonus
        scored.append(
            (
                score,
                str(path.relative_to(reader.root)),
                f"Local evidence file in the week folder ({ext.lstrip('.') or 'file'}"
                f", {path.stat().st_size} bytes).",
                str(path.relative_to(reader.root)),
            )
        )

    for record in collection.records:
        if record.is_holiday or not record.attachments.strip():
            continue
        for line in record.attachments.splitlines():
            entry = line.strip().lstrip("0123456789. ").strip()
            if not entry:
                continue
            path_match = re.search(r"`([^`]+\.(?:md|pdf|png|jpg|jpeg|mp4|mov|xlsx|docx))`", entry)
            if path_match:
                rel = path_match.group(1)
                exists = (reader.root / rel).is_file()
                scored.append(
                    (
                        85.0 if exists else 60.0,
                        rel,
                        f"Referenced in the {record.day.isoformat()} entry"
                        + (" and present locally." if exists else " but not present locally."),
                        rel if exists else None,
                    )
                )
                continue
            if entry.startswith("http"):
                scored.append(
                    (
                        50.0,
                        entry.split()[0],
                        f"Online evidence referenced in the {record.day.isoformat()} entry; "
                        "export or screenshot it before uploading.",
                        None,
                    )
                )
                continue
            scored.append(
                (
                    30.0,
                    entry[:120],
                    f"Named as suggested evidence in the {record.day.isoformat()} entry; "
                    "the file is not in the repository yet.",
                    None,
                )
            )

    if collection.weekly and collection.weekly.suggested_attachments.strip():
        first = next(
            (l for l in collection.weekly.suggested_attachments.splitlines() if l.strip()),
            "",
        )
        entry = first.strip().lstrip("0123456789. ").strip()
        if entry:
            scored.append(
                (
                    40.0,
                    entry[:120],
                    "First item in the week report's own Suggested Attachments list.",
                    None,
                )
            )

    if not scored:
        return AttachmentRecommendation(
            filename="No attachment found",
            reason=(
                "No evidence files exist in attachments/week-"
                f"{collection.number:02d}/ and no daily or weekly entry names any. "
                "Prepare a screenshot or short report from this week's work."
            ),
            status="Missing",
        )

    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, filename, reason, local_path = scored[0]
    status = "Ready" if local_path else "Needs Preparation"
    if not local_path:
        reason += " Prepare or export this evidence before uploading."

    note = ""
    local_count = len([s for s in scored if s[3]])
    if local_count > 1 and max_attachments == 1:
        note = (
            f"{local_count} local evidence files exist for this week. The portal accepts "
            "one attachment: combine them into a single PDF (keeping original page order) "
            "or upload the strongest one only."
        )
    return AttachmentRecommendation(
        filename=filename,
        reason=reason,
        status=status,
        local_path=local_path,
        candidates_considered=len(scored),
        consolidation_note=note,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@dataclass
class ValidationCheck:
    name: str
    status: str
    detail: str


@dataclass
class Submission:
    week: int
    start: date
    end: date
    dailies: list[DailySubmission]
    weekly_summary: str
    weekly_fit: FitResult
    attachment: AttachmentRecommendation
    checks: list[ValidationCheck]
    holidays: dict[str, str]
    missing_days: list[str]
    notes: list[str]
    profile: UniversitySubmissionProfile
    source_summary: str = ""

    @property
    def ok(self) -> bool:
        return all(c.status == PASS for c in self.checks)

    @property
    def summary_count(self) -> int:
        return count_chars(self.weekly_summary)


def _check_dates(collection: WeekCollection, dailies: list[DailySubmission]) -> ValidationCheck:
    problems = []
    if collection.missing:
        problems.append(
            "missing daily record(s): "
            + ", ".join(f"{m.day.isoformat()} ({m.weekday})" for m in collection.missing)
        )
    if not dailies:
        problems.append("no working-day submissions produced")
    seen: set[date] = set()
    for d in dailies:
        if d.day in seen:
            problems.append(f"duplicate submission for {d.day.isoformat()}")
        seen.add(d.day)
        if d.weekday != d.day.strftime("%A"):
            problems.append(f"{d.day.isoformat()} labelled {d.weekday}")
    if collection.holidays:
        problems.append(
            "holidays excluded: " + ", ".join(sorted(collection.holidays))
        )
        # holidays are informational, not a failure
    hard = [p for p in problems if not p.startswith("holidays excluded")]
    return ValidationCheck(
        "Dates",
        ATTENTION if hard else PASS,
        "; ".join(problems) if problems else f"{len(dailies)} working day(s) matched",
    )


def _check_daily_details(dailies: list[DailySubmission]) -> ValidationCheck:
    problems = []
    complete = [d for d in dailies if not d.incomplete]
    for d in complete:
        if not d.task_text.strip():
            problems.append(f"{d.day.isoformat()} has an empty task detail")
    incomplete = [d.day.isoformat() for d in dailies if d.incomplete]
    if incomplete:
        problems.append("incomplete day(s), no task detail: " + ", ".join(incomplete))
    texts = [normalise_for_compare(d.task_text) for d in dailies]
    dupes = {t for t in texts if t and texts.count(t) > 1}
    if dupes:
        problems.append("identical task detail text used on more than one day")
    return ValidationCheck(
        "Daily task details",
        ATTENTION if problems else PASS,
        "; ".join(problems)
        if problems
        else f"{len(complete)} detail(s) generated from source records",
    )


def _check_char_limits(
    dailies: list[DailySubmission], summary: str, profile: UniversitySubmissionProfile
) -> ValidationCheck:
    problems = []
    for d in dailies:
        if d.count > profile.daily_task_char_limit:
            problems.append(f"{d.day.isoformat()} {d.count}/{profile.daily_task_char_limit}")
    if count_chars(summary) > profile.weekly_summary_char_limit:
        problems.append(f"weekly summary {count_chars(summary)}/{profile.weekly_summary_char_limit}")
    return ValidationCheck(
        "Character limits",
        ATTENTION if problems else PASS,
        "; ".join(problems)
        if problems
        else (
            f"max daily {max((d.count for d in dailies), default=0)}/"
            f"{profile.daily_task_char_limit}, summary {count_chars(summary)}/"
            f"{profile.weekly_summary_char_limit}"
        ),
    )


def _check_hours(dailies: list[DailySubmission]) -> ValidationCheck:
    complete = [d for d in dailies if not d.incomplete]
    problems = [d.day.isoformat() for d in complete if d.hours is None]
    if problems:
        return ValidationCheck(
            "Total hours",
            ATTENTION,
            "hours not recorded for " + ", ".join(problems) + " (not assumed)",
        )
    total = sum(d.hours for d in complete if d.hours is not None)
    return ValidationCheck(
        "Total hours", PASS, f"{format_hours(total)} across {len(complete)} day(s)"
    )


def _check_summary(
    summary: str, dailies: list[DailySubmission], profile: UniversitySubmissionProfile
) -> ValidationCheck:
    problems = []
    if not summary.strip():
        problems.append("weekly summary is empty")
    count = count_chars(summary)
    if count > profile.weekly_summary_char_limit:
        problems.append(f"{count}/{profile.weekly_summary_char_limit}")
    daily_sentences = {normalise_for_compare(s) for d in dailies for s in split_sentences(d.task_text)}
    repeated = [
        s
        for s in split_sentences(summary)
        if len(s) > 40 and normalise_for_compare(s) in daily_sentences
    ]
    if repeated:
        problems.append(f"{len(repeated)} sentence(s) copied verbatim from daily task details")
    return ValidationCheck(
        "Weekly summary",
        ATTENTION if problems else PASS,
        "; ".join(problems) if problems else f"{count}/{profile.weekly_summary_char_limit} characters",
    )


def _check_attachment(rec: AttachmentRecommendation, profile: UniversitySubmissionProfile) -> ValidationCheck:
    if rec.status == "Missing":
        return ValidationCheck("Single attachment", ATTENTION, rec.reason)
    if profile.max_weekly_attachments != 1:
        return ValidationCheck(
            "Single attachment",
            ATTENTION,
            f"profile allows {profile.max_weekly_attachments}; portal accepts 1",
        )
    status = PASS if rec.status == "Ready" else ATTENTION
    return ValidationCheck("Single attachment", status, f"{rec.filename} ({rec.status})")


def _check_source_accuracy(
    collection: WeekCollection, dailies: list[DailySubmission], summary: str
) -> ValidationCheck:
    problems = []
    by_day = {r.day: r for r in collection.records}
    for d in dailies:
        if d.incomplete:
            continue
        record = by_day.get(d.day)
        if record is None:
            problems.append(f"{d.day.isoformat()} has no source record")
            continue
        if record.total_hours != d.hours:
            problems.append(f"{d.day.isoformat()} hours differ from source")
        source_words = words(record.combined_text())
        sub_words = words(d.task_text)
        if sub_words and len(sub_words & source_words) / len(sub_words) < 0.9:
            problems.append(f"{d.day.isoformat()} contains wording not in its source record")
    week_text = "\n".join(r.combined_text() for r in collection.records)
    stray_bugs = {b for b in _BUG_ID.findall(summary)} - set(_BUG_ID.findall(week_text))
    if stray_bugs:
        problems.append("summary cites unrecorded identifiers: " + ", ".join(sorted(stray_bugs)))
    return ValidationCheck(
        "Source accuracy",
        ATTENTION if problems else PASS,
        "; ".join(problems)
        if problems
        else f"{len(dailies)} day(s) traceable to daily records; no unrecorded defects cited",
    )


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class SubmissionGenerator:
    """Build one week (or one day) of copy-ready university submission text."""

    def __init__(self, root: str | Path, profile: UniversitySubmissionProfile):
        self.reader = LogbookReader(root, profile)
        self.profile = profile

    # -- public API -------------------------------------------------------
    def generate(
        self,
        week: Optional[int] = None,
        summary_text: Optional[str] = None,
        today: Optional[date] = None,
    ) -> Submission:
        if not self.profile.submission_enabled:
            raise RuntimeError("University submission is disabled in the profile")
        self.profile.validate()
        week = week or self.reader.current_week(today)
        collection = self.reader.collect_week(week)

        dailies: list[DailySubmission] = []
        notes: list[str] = list(self.profile.warnings)
        by_day = {r.day: r for r in collection.records if not r.is_holiday}
        # Every expected working day gets a slot, in date order. A day with no
        # record is marked incomplete and still shown, never filled in.
        for expected in collection.expected_days:
            if expected.isoformat() in collection.holidays:
                continue
            record = by_day.get(expected)
            if record is None:
                dailies.append(
                    DailySubmission(
                        day=expected,
                        weekday=WEEKDAY_NAMES[expected.weekday()],
                        hours=None,
                        task_text="",
                        source_path="",
                        fit=FitResult(
                            text="",
                            limit=self.profile.daily_task_char_limit,
                            original_count=0,
                            final_count=0,
                        ),
                        incomplete=True,
                    )
                )
                continue
            text, fit = compose_daily_task(
                record,
                limit=self.profile.daily_task_char_limit,
                target=None,
            )
            if fit.changed:
                notes.append(f"{record.day.isoformat()}: {fit.summary()}")
            dailies.append(
                DailySubmission(
                    day=record.day,
                    weekday=record.weekday,
                    hours=record.total_hours,
                    task_text=text,
                    source_path=str(record.path.relative_to(self.reader.root)),
                    fit=fit,
                    issues=split_sentences(record.issue)[:2],
                )
            )

        if summary_text is not None:
            # An authored summary is kept in full: only the hard limit applies,
            # not the drafting safety margin, so no paragraph is dropped.
            fit = fit_to_limit(
                summary_text,
                limit=self.profile.weekly_summary_char_limit,
                target=None,
            )
            summary = fit.text
            summary_notes = [fit.summary()] if fit.changed else []
        else:
            summary, fit, summary_notes = draft_weekly_summary(
                collection,
                limit=self.profile.weekly_summary_char_limit,
                target_min=self.profile.target_min_chars,
                target_max=self.profile.target_max_chars,
            )
        notes.extend(summary_notes)

        attachment = recommend_attachment(
            self.reader, collection, self.profile.max_weekly_attachments
        )
        checks = [
            _check_dates(collection, dailies),
            _check_daily_details(dailies),
            _check_char_limits(dailies, summary, self.profile),
            _check_hours(dailies),
            _check_summary(summary, dailies, self.profile),
            _check_attachment(attachment, self.profile),
            _check_source_accuracy(collection, dailies, summary),
        ]

        return Submission(
            week=week,
            start=collection.start,
            end=collection.end,
            dailies=dailies,
            weekly_summary=summary,
            weekly_fit=fit,
            attachment=attachment,
            checks=checks,
            holidays=collection.holidays,
            missing_days=[m.day.isoformat() for m in collection.missing],
            notes=notes,
            profile=self.profile,
            source_summary=(
                f"{len(collection.records)} record(s) read; "
                f"{len(collection.missing)} working day(s) missing"
            ),
        )

    def generate_day(self, day: date) -> DailySubmission:
        self.profile.validate()
        record = self.reader.read_daily(day)
        if record is None:
            raise FileNotFoundError(f"daily/{day.isoformat()}.md does not exist")
        if record.is_holiday:
            raise ValueError(f"{day.isoformat()} is recorded as a public holiday")
        text, fit = compose_daily_task(
            record,
            limit=self.profile.daily_task_char_limit,
            target=self.profile.target_max_chars,
        )
        return DailySubmission(
            day=day,
            weekday=record.weekday,
            hours=record.total_hours,
            task_text=text,
            source_path=str(record.path.relative_to(self.reader.root)),
            fit=fit,
            issues=split_sentences(record.issue)[:2],
        )


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def render_day_block(index: int, submission: DailySubmission, limit: int) -> str:
    if submission.incomplete:
        heading = f"DAY {index} — {submission.weekday.upper()} (INCOMPLETE - NO DAILY RECORD)"
        note = (
            f"Note: no daily record exists for {submission.day.isoformat()}. "
            "Do not submit this day until the notes are written; nothing was invented."
        )
        return "\n".join(
            [
                heading,
                f"Date: {submission.day.isoformat()}",
                "Total Hours: NOT RECORDED",
                f"Character Count: 0 / {limit}",
                note,
                "",
                "TASK DETAILS:",
                "",
            ]
        )
    lines = [
        f"DAY {index} — {submission.weekday.upper()}",
        f"Date: {submission.day.isoformat()}",
        f"Total Hours: {submission.hours_text}",
        f"Character Count: {submission.count} / {limit}",
        "",
        "TASK DETAILS:",
        submission.task_text,
    ]
    return "\n".join(lines)


def render_submission(sub: Submission) -> str:
    limit_daily = sub.profile.daily_task_char_limit
    limit_weekly = sub.profile.weekly_summary_char_limit
    out: list[str] = [
        f"UNIVERSITY INTERNSHIP SUBMISSION — WEEK {sub.week:02d}",
        f"Period: {sub.start.isoformat()} to {sub.end.isoformat()}",
        "",
        "========================================",
        "DAILY TASK DETAILS",
        "========================================",
        "",
    ]
    if not sub.dailies:
        out.append("No daily task details could be generated: no daily records exist for this week.")
        out.append("")
    for i, day in enumerate(sub.dailies, start=1):
        out.append(render_day_block(i, day, limit_daily))
        out.append("")
        out.append("----------------------------------------")
        out.append("")
    out.extend(
        [
            "========================================",
            "WEEKLY SUMMARY",
            "========================================",
            f"Character Count: {sub.summary_count} / {limit_weekly}",
            "",
            sub.weekly_summary or "No weekly summary could be generated from the available records.",
            "",
            "========================================",
            "WEEKLY ATTACHMENT",
            "========================================",
            f"Recommended File: {sub.attachment.filename}",
            f"Reason: {sub.attachment.reason}",
            f"Upload Status: {sub.attachment.status}",
        ]
    )
    if sub.attachment.consolidation_note:
        out.append(f"Note: {sub.attachment.consolidation_note}")
    out.extend(
        [
            "",
            "========================================",
            "END OF COPY-READY CONTENT",
            "Everything above this line is submission text.",
            "Everything below it is for your eyes only - do not paste it.",
            "========================================",
            "",
            "========================================",
            "WARNINGS AND VALIDATION",
            "========================================",
        ]
    )
    for check in sub.checks:
        out.append(f"- {check.name}: {check.status} — {check.detail}")
    if sub.holidays:
        out.append("")
        out.append(
            "Public holidays excluded: "
            + ", ".join(f"{d} ({name})" for d, name in sorted(sub.holidays.items()))
        )
    if sub.missing_days:
        out.append(
            "Missing daily records: "
            + ", ".join(sub.missing_days)
            + " — supply the raw notes for these dates; nothing was invented."
        )
    if sub.notes:
        out.append("")
        out.append("NOTES")
        for note in sub.notes:
            out.append(f"- {note}")
    out.append("")
    out.append(
        "Reminder: remove confidential company information and personal data "
        "(names, emails, phone numbers, IDs, credentials) from any attachment "
        "before uploading. Nothing here has been submitted to the portal."
    )
    return "\n".join(out).rstrip() + "\n"


def render_day_only(sub: DailySubmission, limit: int, index: int = 1) -> str:
    return render_day_block(index, sub, limit) + "\n"


def render_validation(sub: Submission) -> str:
    lines = [f"VALIDATION — WEEK {sub.week:02d} ({sub.start.isoformat()} to {sub.end.isoformat()})"]
    for check in sub.checks:
        lines.append(f"- {check.name}: {check.status} — {check.detail}")
    if sub.missing_days:
        lines.append("- Missing daily records: " + ", ".join(sub.missing_days))
    lines.append(f"- Overall: {'PASS' if sub.ok else ATTENTION}")
    return "\n".join(lines)
