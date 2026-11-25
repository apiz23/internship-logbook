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
    DETAILED_DAILY_MAX,
    PREFERRED_DAILY_MAX,
    PREFERRED_DAILY_MIN,
    PREFERRED_WEEKLY_MAX,
    PREFERRED_WEEKLY_MIN,
    FitResult,
    check_limit,
    count_chars,
    fit_to_limit,
    length_band,
    normalise_newlines,
)
from concise import (
    clean_line,
    clean_text,
    collect_bug_ids,
    drop_heading_only_blocks,
    is_administrative_noise,
    summarise_blocks,
    summarise_sequential,
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
_LIST_MARKER = re.compile(r"(?m)^([ \t]*(?:\d{1,3}|[A-Za-z])[.)])[ \t]+")
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
# Supervisor-facing wording for each activity family.
_ACTIVITY_LABELS = {
    "testing": "functional and regression testing",
    "debugging": "defect investigation",
    "documentation": "documentation",
    "research": "research and review",
    "development": "development work",
    "automation": "automation work",
}
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’.\-/%]*")


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def split_sentences(text: str) -> list[str]:
    """Split prose into sentences, keeping list markers attached to their text.

    ``1. Findings`` stays whole; splitting on the period alone produces a
    bare ``1.`` plus an orphan.
    """
    markers: list[str] = []

    def _protect(match: re.Match[str]) -> str:
        markers.append(match.group(1))
        return f"\x00{len(markers) - 1}\x00 "

    protected = _LIST_MARKER.sub(_protect, normalise_newlines(text or ""))
    flat = _WS.sub(" ", protected).strip()
    if not flat:
        return []
    out = []
    for part in _SENTENCE_END.split(flat):
        if not part.strip():
            continue
        restored = re.sub(r"\x00(\d+)\x00", lambda m: markers[int(m.group(1))], part)
        out.append(restored.strip())
    return out


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
    generic = re.compile(
        r"workstreams? (?:were|was)|work continued|the day (?:began|started|covered)|"
        r"today'?s work|continued (?:manual|with)",
        re.I,
    )
    for sentence in split_sentences(record.task_detail or record.raw_notes)[:4]:
        if generic.search(sentence):
            continue
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
            # A status is a state, not a sentence: drop the qualifier in
            # brackets so the line never renders half-open.
            clean = clean.split("(")[0].strip()
            label = " ".join(clean.split()[:4])
            if not label:
                continue
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
    authored: bool = False
    preferred_max: int = 0

    @property
    def count(self) -> int:
        return count_chars(self.task_text)

    @property
    def band(self) -> str:
        """Concise / Detailed / Over limit for the measured field."""
        return length_band(
            self.count, self.preferred_max or self.fit.limit, self.fit.limit
        )

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


_HEADING_BLOCK = re.compile(
    r"^(?:[A-Z][.)]|\d+[.)]|#{1,6}\s|(?:Workstream|Section|Part|Block|Phase|Appendix)\b)",
    re.I,
)


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


def _subsection(body: str, name: str) -> str:
    """Return one ``### Name`` subsection's text from a day report body."""
    pattern = re.compile(
        r"^#{2,6}\s*" + re.escape(name) + r"\s*$([\s\S]*?)(?=^#{2,6}\s|\Z)",
        re.M | re.I,
    )
    match = pattern.search(body or "")
    return match.group(1).strip() if match else ""


def weekly_day_parts(
    collection: WeekCollection, day: date
) -> tuple[str, str]:
    """The week report's own Task Detail and Issue text for one day.

    The report restates each day in finished prose. It is only used when the
    raw daily record cannot supply a readable field, and it is still the same
    day's work - never another day's.
    """
    if collection.weekly is None or not collection.weekly.days:
        return "", ""
    wanted = f"{day.strftime('%A').lower()}"
    for heading, body in collection.weekly.days.items():
        if heading.strip().lower().startswith(wanted):
            return _subsection(body, "task detail"), _subsection(body, "issue")
    return "", ""


def _join_ids(ids: list[str]) -> str:
    if not ids:
        return ""
    if len(ids) == 1:
        return ids[0]
    if len(ids) == 2:
        return f"{ids[0]} and {ids[1]}"
    return ", ".join(ids[:-1]) + " and " + ids[-1]


def _tidy_paragraphs(text: str) -> str:
    """Close dangling lead-ins and give every paragraph terminal punctuation.

    A record can end a selected sentence on a colon whose bullet list was
    dropped as administrative noise, which renders as "... carried to a
    verdict with evidence" and stops dead.
    """
    out: list[str] = []
    for raw in (text or "").split("\n\n"):
        para = raw.strip()
        if not para:
            continue
        while para.endswith(":"):
            sentences = split_sentences(para)
            sentences = [s for s in sentences if s.rstrip().endswith(":") is False]
            para = " ".join(sentences).strip()
            if not para:
                break
        if not para:
            continue
        if para[-1] not in ".!?\"'":
            para = para.rstrip(" ,;:") + "."
        out.append(para)
    return "\n\n".join(out)


def _balance_parens(text: str) -> str:
    """Drop an unclosed parenthetical instead of leaving it half-open.

    Trimming a clause can land inside brackets, which renders as
    "Status: Completed (discovery, deduplication, per-URL." — a fragment that
    reads as broken rather than shortened.
    """
    text = (text or "").rstrip()
    if text.count("(") == text.count(")"):
        return text
    depth = 0
    open_at = -1
    for i, ch in enumerate(text):
        if ch == "(":
            if depth == 0:
                open_at = i
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
    if depth and open_at > 0:
        return text[:open_at].rstrip(" ,;:-")
    return text


def _trim_clause(text: str, max_chars: int) -> str:
    """Cut a long statement at a natural clause boundary."""
    text = text.strip()
    if len(text) <= max_chars:
        return _balance_parens(text)
    cut = text[:max_chars]
    # Prefer a whole sentence, then a clause, so the blocker never ends on a
    # dangling word like "never" or "not".
    stop = max(cut.rfind(". "), cut.rfind("; "), cut.rfind(", "), cut.rfind(" and "))
    trimmed = cut[:stop] if stop > max_chars * 0.4 else cut[: cut.rfind(" ")]
    words = trimmed.rstrip(" ,;.").split()
    while words and words[-1].lower().strip(",;:") in {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "from",
        "with", "as", "at", "by", "that", "which", "is", "was", "were", "be",
        "never", "not", "only", "also", "but",
    }:
        words.pop()
    return _balance_parens(" ".join(words).rstrip(" ,;"))


def _first_useful_sentence(text: str, max_chars: int = 220) -> str:
    """First line of a section that states the issue, without headings.

    Section titles, bullet markers and metadata lines are skipped so the
    rendered blocker reads as a finding rather than as leftover Markdown.
    """
    for raw in to_plain_text(text).splitlines():
        line = clean_line(raw).strip()
        if len(line) < 25 or is_administrative_noise(line):
            continue
        # A lead-in ("Three defects were identified:") names nothing; the
        # bullet under it carries the finding.
        # A short line with no full stop is a lead-in, not a finding.
        if len(line.split()) <= 9 and not line.endswith((".", "!", "?")):
            continue
        sentences = split_sentences(line)
        first = sentences[0] if sentences else line
        if is_administrative_noise(first) or first.endswith(":"):
            continue
        # A sentence that stops on a function word is cut off in the source.
        if first[:1].islower():
            continue
        tail = first.rstrip(" .;:").split()
        if len(tail) < 5:
            continue
        if tail and tail[-1].lower() in {
            "the", "a", "an", "and", "or", "of", "to", "in", "on", "for",
            "from", "with", "as", "at", "by", "that", "which", "never", "not",
        }:
            continue
        return _trim_clause(first.rstrip(" .;:"), max_chars)
    return ""


def compose_daily_task(
    record: DailyRecord,
    limit: int = DEFAULT_LIMIT,
    target: Optional[int] = None,
    include_context: bool = True,
    preferred_min: int = PREFERRED_DAILY_MIN,
    preferred_max: int = PREFERRED_DAILY_MAX,
    detailed_max: int = DETAILED_DAILY_MAX,
    report_detail: str = "",
    report_issue: str = "",
) -> tuple[str, FitResult]:
    """Build one concise day's task detail from its daily record.

    The portal's 4,000 characters are a ceiling, not a quota: the field is a
    short account of the day, normally 500-1,200 characters and up to 1,500
    on a genuinely busy or technically complex day. Selection is extractive,
    so every sentence comes from the record; administrative detail (URLs,
    timestamps, file paths, identifier dumps) is dropped first and findings,
    defects and blockers are kept.
    """
    base = record.task_detail.strip() or record.raw_notes.strip()
    if not base:
        return "", fit_to_limit("", limit=limit)

    plain = clean_text(to_plain_text(drop_heading_only_blocks(base)))
    result = summarise_sequential(
        plain,
        min_chars=preferred_min,
        max_chars=preferred_max,
        busy_max_chars=detailed_max,
    )

    # Raw notes can be too fragmented to read (bulleted tables, one-line
    # labels). When the week report holds a written summary of the *same*
    # day, that prose is the better base; the daily record still decides
    # hours, defects and blockers.
    if report_detail and count_chars(result.text) < preferred_max:
        alt_plain = clean_text(to_plain_text(report_detail))
        alt = summarise_sequential(
            alt_plain,
            min_chars=preferred_min,
            max_chars=preferred_max,
            busy_max_chars=detailed_max,
        )
        # The report restates the same day in finished prose; when it gives a
        # fuller account than the raw-notes extraction, it is the better base.
        if count_chars(alt.text) > count_chars(result.text) + 40:
            result = alt
            plain = alt_plain

    parts: list[str] = [result.text] if result.text else []

    # Group defects instead of leaving scattered mentions: one line, real IDs.
    bug_ids = collect_bug_ids(plain)
    if len(bug_ids) >= 2 and not any(b in result.text for b in bug_ids):
        parts.append(f"Defects recorded: {_join_ids(bug_ids)}.")

    if include_context:
        issue_text = normalise_for_compare(" ".join(parts))
        blocker = _first_useful_sentence(record.issue) or _first_useful_sentence(
            report_issue
        )
        if (
            blocker
            and normalise_for_compare(blocker) not in issue_text
            and not is_administrative_noise(blocker)
        ):
            # Keep the blocker short: its first sentence is the statement.
            parts.append(f"Blocker: {blocker.rstrip(' .;:')}.")
        status = _status_label(record)
        if status and normalise_for_compare(f"status: {status}") not in issue_text:
            parts.append(f"Status: {status}.")

    body = _tidy_paragraphs(
        "\n\n".join(part.strip() for part in parts if part.strip())
    )
    # The preferred maximum is the writing budget; the hard portal limit is
    # enforced again here on the FINAL text, never on the draft.
    fit = fit_to_limit(
        body,
        limit=limit,
        target=detailed_max if count_chars(body) > detailed_max else None,
    )
    final_text = renumber_ordered_items(drop_orphan_headings(fit.text))
    if final_text != fit.text:
        fit.text = final_text
        fit.final_count = count_chars(final_text)
        if fit.final_count > limit:
            fit = fit_to_limit(final_text, limit=limit)
    return fit.text, fit


# ---------------------------------------------------------------------------
# Weekly summary
# ---------------------------------------------------------------------------


_NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
_CLAIMED_DEFECTS = re.compile(
    r"\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+"
    r"(?:defects?|bugs?)\s+(?:were\s+|was\s+)?"
    r"(?:reported|recorded|raised|logged|found|identified)",
    re.I,
)


def claimed_defect_count(text: str) -> Optional[int]:
    """Defect total a piece of text claims, if it states one explicitly."""
    match = _CLAIMED_DEFECTS.search(text or "")
    if not match:
        return None
    token = match.group(1).lower()
    if token.isdigit():
        return int(token)
    return _NUM_WORDS.get(token)


def draft_weekly_summary(
    collection: WeekCollection,
    limit: int = DEFAULT_LIMIT,
    target_min: int = PREFERRED_WEEKLY_MIN,
    target_max: int = PREFERRED_WEEKLY_MAX,
) -> tuple[str, FitResult, list[str]]:
    """Draft a concise weekly summary (normally 800-1,500 characters).

    The summary reports the week, not the days: it states the period and
    hours, the projects and kinds of work involved, what each day focused on
    in one clause, the outcomes and defect count, the blockers, and how the
    week closed. Sentences are assembled from aggregated facts and short
    topic clauses, so the summary does not repeat the daily fields verbatim.
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

    paragraphs: list[str] = []

    span = (
        f"Week {collection.number} covered {len(active)} working days from "
        f"{_date_label(collection.start)} to {_date_label(collection.end)}"
    )
    if totals is not None and len(recorded_hours) == len(active):
        span += f", with {format_hours(totals)} recorded."
    elif totals is not None:
        span += (
            f", with {format_hours(totals)} recorded across "
            f"{len(recorded_hours)} of those days."
        )
    else:
        span += "."
    paragraphs.append(span)

    week_text = "\n".join(r.combined_text() for r in active)

    # The week report already contains a written summary. It is context, not
    # authority: it is condensed to the preferred range and cross-checked
    # against the daily records, which stay the source of truth.
    report_summary = ""
    if collection.weekly is not None:
        # Keep the report's own paragraph breaks: each paragraph lead is a
        # theme, and collapsing them to one block loses whole topics.
        report_summary = (collection.weekly.summary or "").strip()
    if count_chars(report_summary) >= 300:
        blocks = [span] + [
            block for block in report_summary.split("\n\n") if block.strip()
        ]
        result = summarise_blocks(
            blocks,
            min_chars=target_min,
            max_chars=target_max,
            lead_sentences=1,
            per_paragraph=2,
        )
        fit = fit_to_limit(result.text, limit=limit, target=target_max)
        if fit.changed:
            notes.append(fit.summary())
        unique_bugs = sorted(set(_BUG_ID.findall(week_text)))
        claimed = claimed_defect_count(fit.text)
        if claimed is not None and unique_bugs and claimed != len(unique_bugs):
            notes.append(
                f"Week report states {claimed} defects; the daily records contain "
                f"{len(unique_bugs)} distinct defect IDs. The report's total was "
                "replaced with a count taken from the daily records."
            )
            # Drop the sentence carrying the wrong total; the daily records
            # decide the number, and a count is restated from them.
            kept_blocks: list[str] = []
            for block in fit.text.split("\n\n"):
                sentences = [
                    s
                    for s in split_sentences(block)
                    if claimed_defect_count(s) is None
                ]
                if sentences:
                    kept_blocks.append(" ".join(sentences))
            noun = "defect" if len(unique_bugs) == 1 else "defects"
            restated = (
                f"{len(unique_bugs)} {noun} were recorded across the week "
                f"({_join_ids(unique_bugs[:5])}"
                f"{', among others' if len(unique_bugs) > 5 else ''})."
            )
            rebuilt = "\n\n".join(kept_blocks + [restated])
            fit = fit_to_limit(rebuilt, limit=limit, target=target_max)
            if fit.changed:
                notes.append(fit.summary())
        if count_chars(fit.text) < target_min:
            notes.append(
                f"Summary is {count_chars(fit.text)} characters, below the preferred "
                f"{target_min}-{target_max}; nothing was added to pad it."
            )
        return fit.text, fit, notes

    projects = _projects_in(week_text)
    lowered = week_text.lower()
    activity_labels = [
        _ACTIVITY_LABELS[name]
        for name, needles in _ACTIVITY_KEYWORDS.items()
        if any(needle in lowered for needle in needles)
    ]
    focus: list[str] = []
    if projects:
        focus.append("Work continued on " + _join_ids(projects))
    if activity_labels:
        focus.append("The week covered " + _join_ids(activity_labels))
    if focus:
        paragraphs.append(". ".join(focus) + ".")

    # Aggregates alone read like a status page. The portal summary is expected
    # to say what the week's work actually consisted of, so each day keeps one
    # clause taken from its own record — never from another day's.
    day_clauses: list[str] = []
    for record in active:
        source = record.task_detail.strip() or record.raw_notes.strip()
        if not source:
            continue
        plain_day = clean_text(to_plain_text(drop_heading_only_blocks(source)))
        candidates = [
            s
            for s in split_sentences(plain_day)
            if len(s.split()) >= 6
            and not is_administrative_noise(s)
            and not s.rstrip().endswith(":")
            and not re.search(r"\b(?:and|or|the|of|to|with|for)$", s.rstrip())
        ]
        if not candidates:
            continue
        clause = _trim_clause(candidates[0].rstrip(" .;:"), 190)
        if not clause or len(clause.split()) < 5:
            continue
        lowered = clause.lower()
        for opener in _DAY_OPENERS:
            if lowered.startswith(opener):
                clause = clause[len(opener):].lstrip()
                lowered = clause.lower()
                break
        if not clause or len(clause.split()) < 5:
            continue
        clause = _lower_first(clause) if clause[:1].isupper() else clause
        day_clauses.append(f"{record.weekday} — {clause}")
    if day_clauses:
        paragraphs.append("Day by day: " + "; ".join(day_clauses) + ".")


    bug_ids = sorted(set(_BUG_ID.findall(week_text)))
    case_ids = sorted(
        {
            token
            for token in re.findall(r"\b[A-Z]{2,4}-\d{1,3}\b", week_text)
            if not token.startswith("BUG-")
        }
    )
    outcomes: list[str] = []
    if bug_ids:
        noun = "defect" if len(bug_ids) == 1 else "defects"
        ids_note = (
            f" ({_join_ids(bug_ids[:4])}{', among others' if len(bug_ids) > 4 else ''})"
        )
        outcomes.append(f"{len(bug_ids)} {noun} were recorded{ids_note}")
    if len(case_ids) >= 3:
        outcomes.append(f"{len(case_ids)} individual test cases were referenced")
    status_counts: dict[str, int] = {}
    for record in active:
        label = _status_label(record)
        if label:
            status_counts[label] = status_counts.get(label, 0) + 1
    if status_counts:
        ordered_status = sorted(status_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        pieces = [
            f"{label} on {count} day{'s' if count != 1 else ''}"
            for label, count in ordered_status
        ]
        outcomes.append("work closed as " + _join_ids(pieces))
    if outcomes:
        paragraphs.append("; ".join(outcomes) + ".")

    themes: list[str] = []
    seen_themes: set[str] = set()
    for record in active:
        for theme in _issue_themes(record, max_items=1):
            key = " ".join(normalise_for_compare(theme).split()[:4])
            if key and key not in seen_themes and not is_administrative_noise(theme):
                seen_themes.add(key)
                themes.append(theme)
    blocker_days = [r for r in active if _first_useful_sentence(r.issue)]
    if blocker_days:
        sentence = (
            f"Blocking issues were recorded on {len(blocker_days)} of "
            f"{len(active)} days"
        )
        if themes:
            sentence += ", including " + themes[0]
        paragraphs.append(sentence + ".")

    if len(recorded_hours) < len(active) and recorded_hours:
        paragraphs.append(
            "Recorded hours were incomplete for the week, so no daily total was assumed."
        )

    draft = _tidy_paragraphs("\n\n".join(p for p in paragraphs if p.strip()))
    fit = fit_to_limit(draft, limit=limit, target=target_max)
    if fit.changed:
        notes.append(fit.summary())
    if count_chars(fit.text) < target_min:
        notes.append(
            f"Summary is {count_chars(fit.text)} characters, below the preferred "
            f"{target_min}-{target_max}; nothing was added to pad it."
        )
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
    canonical_map = {
        "ocare": "O'Care",
        "otalk": "OTalk",
        "ozone": "O'Zone",
        "kiwi import": "Kiwi Import",
        "hermes": "Hermes",
        "creator research": "Creator Research",
        "ochat": "OChat",
    }
    found: list[str] = []
    seen: set[str] = set()
    lowered = text.lower()
    for name in pool:
        if re.search(rf"(?<![a-z0-9]){re.escape(name.lower())}(?![a-z0-9])", lowered):
            canonical = canonical_map.get(name.lower(), name)
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

    @property
    def summary_band(self) -> str:
        return length_band(
            self.summary_count,
            self.profile.weekly_summary_preferred_max,
            self.profile.weekly_summary_char_limit,
        )


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
    if problems:
        return ValidationCheck("Character limits", ATTENTION, "; ".join(problems))
    max_daily = max((d.count for d in dailies), default=0)
    daily_band = length_band(
        max_daily,
        profile.daily_task_preferred_max,
        profile.daily_task_char_limit,
    )
    summary_band = length_band(
        count_chars(summary),
        profile.weekly_summary_preferred_max,
        profile.weekly_summary_char_limit,
    )
    detailed = [
        d.day.isoformat() for d in dailies if d.band == "Detailed"
    ]
    detail = (
        f"max daily {max_daily}/{profile.daily_task_char_limit} ({daily_band}), "
        f"summary {count_chars(summary)}/{profile.weekly_summary_char_limit} "
        f"({summary_band}); preferred daily {profile.daily_task_preferred_min}-"
        f"{profile.daily_task_preferred_max}, summary "
        f"{profile.weekly_summary_preferred_min}-"
        f"{profile.weekly_summary_preferred_max}"
    )
    if detailed:
        detail += "; above preferred but acceptable: " + ", ".join(detailed)
    return ValidationCheck("Character limits", PASS, detail)


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
    summary: str,
    dailies: list[DailySubmission],
    profile: UniversitySubmissionProfile,
    week_text: str = "",
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
    week_bugs = set(_BUG_ID.findall(week_text)) or {
        b for d in dailies for b in _BUG_ID.findall(d.task_text)
    }
    claimed = claimed_defect_count(summary)
    if claimed is not None and week_bugs and claimed != len(week_bugs):
        problems.append(
            f"summary states {claimed} defects but the daily fields name "
            f"{len(week_bugs)}"
        )
    if problems:
        return ValidationCheck("Weekly summary", ATTENTION, "; ".join(problems))
    band = length_band(
        count, profile.weekly_summary_preferred_max, profile.weekly_summary_char_limit
    )
    detail = (
        f"{count}/{profile.weekly_summary_char_limit} characters ({band}), "
        f"preferred {profile.weekly_summary_preferred_min}-"
        f"{profile.weekly_summary_preferred_max}"
    )
    if count < profile.weekly_summary_preferred_min:
        detail += "; shorter than preferred, nothing was added to pad it"
    return ValidationCheck("Weekly summary", PASS, detail)


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
        # Authored prose may rephrase, so it is checked for traceability at a
        # lower overlap; generated text must stay almost verbatim.
        # Generated fields are condensed prose rebuilt from the same day's
        # record (daily notes or that day's report section), so traceability
        # is measured at a lower overlap than a near-verbatim copy.
        threshold = 0.6 if d.authored else 0.75
        if sub_words and len(sub_words & source_words) / len(sub_words) < threshold:
            problems.append(
                f"{d.day.isoformat()} contains wording not in its source record"
            )
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
        daily_overrides: Optional[dict[date, str]] = None,
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
                        preferred_max=self.profile.daily_task_preferred_max,
                    )
                )
                continue
            override = (daily_overrides or {}).get(record.day)
            if override is not None:
                # Authored field: keep it in full, measure the final text.
                fit = fit_to_limit(
                    override,
                    limit=self.profile.daily_task_char_limit,
                    target=None,
                )
                text = fit.text
                authored = True
                notes.append(
                    f"{record.day.isoformat()}: authored text, "
                    f"{fit.final_count}/{self.profile.daily_task_char_limit}"
                )
            else:
                authored = False
                report_detail, report_issue = weekly_day_parts(
                    collection, record.day
                )
                text, fit = compose_daily_task(
                    record,
                    limit=self.profile.daily_task_char_limit,
                    target=None,
                    preferred_min=self.profile.daily_task_preferred_min,
                    preferred_max=self.profile.daily_task_preferred_max,
                    detailed_max=self.profile.daily_task_detailed_max,
                    report_detail=report_detail,
                    report_issue=report_issue,
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
                    authored=authored,
                    preferred_max=self.profile.daily_task_preferred_max,
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
                target_min=self.profile.weekly_summary_preferred_min,
                target_max=self.profile.weekly_summary_preferred_max,
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
            _check_summary(
                summary,
                dailies,
                self.profile,
                week_text="\n".join(r.combined_text() for r in collection.records),
            ),
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

    def generate_day(
        self,
        day: date,
        daily_overrides: Optional[dict[date, str]] = None,
    ) -> DailySubmission:
        self.profile.validate()
        record = self.reader.read_daily(day)
        if record is None:
            raise FileNotFoundError(f"daily/{day.isoformat()}.md does not exist")
        if record.is_holiday:
            raise ValueError(f"{day.isoformat()} is recorded as a public holiday")
        week = self.reader.week_number_for(day)
        override = (daily_overrides or {}).get(day)
        if override is not None:
            # Authored field: keep it in full, measure the final text.
            fit = fit_to_limit(
                override,
                limit=self.profile.daily_task_char_limit,
                target=None,
            )
            text = fit.text
            authored = True
        else:
            authored = False
            report_detail, report_issue = weekly_day_parts(
                self.reader.collect_week(week), day
            )
            text, fit = compose_daily_task(
                record,
                limit=self.profile.daily_task_char_limit,
                preferred_min=self.profile.daily_task_preferred_min,
                preferred_max=self.profile.daily_task_preferred_max,
                detailed_max=self.profile.daily_task_detailed_max,
                report_detail=report_detail,
                report_issue=report_issue,
            )
        return DailySubmission(
            day=day,
            weekday=record.weekday,
            hours=record.total_hours,
            task_text=text,
            source_path=str(record.path.relative_to(self.reader.root)),
            fit=fit,
            issues=split_sentences(record.issue)[:2],
            authored=authored,
            preferred_max=self.profile.daily_task_preferred_max,
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
                f"Character Count: 0 / {limit} (no text)",
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
        f"Character Count: {submission.count} / {limit} ({submission.band})",
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
            f"Character Count: {sub.summary_count} / {limit_weekly} ({sub.summary_band})",
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
