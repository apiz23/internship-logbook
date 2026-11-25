"""Regression tests for the daily submission field.

The bug these lock down: ``clean_text`` joined hard-wrapped lines with a full
stop, so every wrap in a wrapped record invented a sentence boundary. Records
then read "remaining O'Zone. staging cases", the sentence filter rejected the
wreckage as fragments, and the rendered day collapsed to a few hundred
characters starting mid-list ("713, 735, 857), cases waiting on ...").

Note: ``clean_text`` drops short lines that carry no terminal punctuation
(they are section titles), so every fixture below is written at logbook
length — one long sentence wrapped across lines.
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from concise import clean_text  # noqa: E402
from logbook_reader import LogbookReader  # noqa: E402
from submission_generator import compose_daily_task  # noqa: E402
from university_profile import load_profile  # noqa: E402


def test_hard_wrap_is_joined_with_a_space():
    """A wrapped line is a wrap, not the end of a sentence."""
    wrapped = (
        "The day was split between triage of the remaining O'Zone staging cases across\n"
        "three version tags and execution of a block of app cases on v1.1.0,\n"
        "with one new defect raised against the full screen case."
    )
    text = clean_text(wrapped)
    assert "O'Zone staging cases across three version tags" in text
    assert "cases. across" not in text
    assert "v1.1.0, with one new defect" in text
    # Only the one sentence-terminating full stop the record itself carried.
    assert text.count(". ") == 0


def test_bullet_items_still_start_their_own_sentence():
    """A list item is a statement of its own, so it keeps a separator."""
    bullets = (
        "- **815 (A1)** uploaded a short clip and filled the upload form in full "
        "before submitting it to the staging build\n"
        "- **820 (A6)** opened the more options sheet and set the description, tags "
        "and language on the same clip"
    )
    text = clean_text(bullets)
    assert "upload form in full before submitting it to the staging build. " in text
    assert "820 (A6) opened the more options sheet" in text


def test_clause_separator_survives_line_cleaning():
    """A trailing semicolon between clauses is content, not marker noise."""
    text = clean_text(
        "Counts were read per version first, with v1.1.0 at 58 Done and 33 Not started;\n"
        "v1.1.1 then followed at 101 Done with 36 Not started."
    )
    assert "33 Not started; v1.1.1" in text


@pytest.mark.parametrize(
    "iso,min_chars",
    [
        ("2026-11-24", 900),
        ("2026-11-20", 900),
        ("2026-11-17", 700),
        ("2026-11-06", 500),
    ],
)
def test_real_records_render_readable_prose(iso, min_chars):
    """Whole sentences, no mid-list start, balanced parentheses, real length."""
    year, month, day = (int(part) for part in iso.split("-"))
    path = ROOT / "daily" / f"{iso}.md"
    if not path.exists():
        pytest.skip(f"{iso} is not in this checkout")

    record = LogbookReader(ROOT, load_profile(ROOT)).read_daily(
        __import__("datetime").date(year, month, day)
    )
    if record is None or not (record.task_detail.strip() or record.raw_notes.strip()):
        pytest.skip(f"{iso} has no task detail to render")

    text, _fit = compose_daily_task(record)
    assert len(text) >= min_chars, f"{iso} rendered only {len(text)} characters"

    for paragraph in text.split("\n\n"):
        # Starts a sentence, not the middle of a parenthesised list.
        assert not re.match(r"^\s*\d{1,3}\s*[,)]", paragraph), paragraph[:80]
        # No half-open bracket left behind by a truncation.
        assert paragraph.count("(") == paragraph.count(")"), paragraph[:120]
        # Nothing that stops mid-clause.
        assert not re.search(r"\b(?:and|or|the|of|to|with|for)$", paragraph.strip())

    assert text.rstrip()[-1] in ".!?\""


def test_no_paragraph_stops_on_a_colon():
    """A dropped bullet list must not leave a dangling lead-in."""
    from submission_generator import _tidy_paragraphs  # noqa: E402

    text = _tidy_paragraphs(
        "Eight were carried to a verdict with evidence:\n\n"
        "The next paragraph carries no final stop"
    )
    for para in text.split("\n\n"):
        assert not para.endswith(":"), para
        assert para.endswith("."), para


def test_weekly_summary_is_built_from_the_days():
    """Without a written week report the summary still says what happened."""
    from submission_generator import draft_weekly_summary  # noqa: E402

    week = reader_for_tests().collect_week(17)
    if not week.records:
        pytest.skip("week 17 is not in this checkout")
    text, _fit, _notes = draft_weekly_summary(week)
    assert "Day by day" in text
    assert "working days" in text
    # It must name both days, not just aggregate counts.
    assert "Monday" in text and "Tuesday" in text
    assert len(text) >= 600, f"weekly summary collapsed to {len(text)} characters"


def reader_for_tests():
    return LogbookReader(ROOT, load_profile(ROOT))
