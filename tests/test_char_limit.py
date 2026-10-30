"""Tests for the university-submission character-limit module."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from char_limit import (  # noqa: E402
    DEFAULT_LIMIT,
    check_limit,
    count_chars,
    count_chars_crlf,
    fit_to_limit,
    normalise_newlines,
)


def test_exactly_4000_characters_passes():
    text = "a" * 4000
    result = check_limit(text)
    assert result.count == 4000
    assert result.within_limit is True
    assert result.remaining == 0
    assert result.over_by == 0


def test_4001_characters_fails_with_over_by_one():
    result = check_limit("a" * 4001)
    assert result.count == 4001
    assert result.within_limit is False
    assert result.over_by == 1
    assert result.remaining == -1


def test_spaces_and_newlines_are_counted():
    text = "line one\nline two\n"
    assert text.count(" ") == 2
    assert count_chars(text) == len(text) == 18
    # each newline is one character, not two
    assert count_chars("a\nb") == 3


def test_crlf_normalisation_does_not_double_count():
    assert count_chars("a\r\nb") == 3
    assert normalise_newlines("a\r\nb") == "a\nb"
    # if the portal stores CRLF, the count is higher - reported separately
    assert count_chars_crlf("a\nb") == 4


def test_punctuation_and_unicode_counted_as_characters():
    text = "Implemented the “SOS Alert” settings — 3 bugs fixed ✅"
    assert count_chars(text) == len(text)
    assert check_limit(text).count == len(text)


def test_empty_and_none_input():
    assert count_chars("") == 0
    assert count_chars(None) == 0
    assert check_limit("").within_limit is True


def test_summary_text_reports_counts():
    assert "4001 / 4000" in check_limit("a" * 4001).summary()
    assert "OVER by 1" in check_limit("a" * 4001).summary()
    assert "remaining" in check_limit("abc").summary()


def test_fit_to_limit_leaves_fitting_text_alone():
    text = "A short, complete task description."
    result = fit_to_limit(text)
    assert result.changed is False
    assert result.text == text
    assert result.final_count == count_chars(text)


def test_fit_to_limit_shortens_oversized_text_and_revalidates_final():
    block = (
        "Conducted functional testing of the school filtering feature and compared "
        "the result against the expected case records. "
    )
    text = "\n\n".join(block * 6 for _ in range(12))
    assert count_chars(text) > DEFAULT_LIMIT

    result = fit_to_limit(text)
    # The final text must be measured, not assumed.
    assert result.final_count == count_chars(result.text)
    assert result.final_count <= DEFAULT_LIMIT
    assert result.changed is True


def test_fit_to_limit_respects_target_budget():
    text = "word " * 1200  # 6,000 characters
    result = fit_to_limit(text, limit=4000, target=3800)
    assert result.final_count <= 3800
    assert result.final_count == count_chars(result.text)


def test_fit_to_limit_keeps_leading_block():
    head = "Daily summary for the production defect review."
    body = "\n\n".join(f"Extra detail block {i} about testing." for i in range(60))
    result = fit_to_limit(head + "\n\n" + body, limit=400)
    assert result.text.startswith(head)


def test_fit_to_limit_never_exceeds_limit_for_long_unbroken_text():
    text = "x" * 5000
    result = fit_to_limit(text, limit=1000)
    assert result.final_count <= 1000
    assert result.within_limit is True
    assert result.hard_truncated is True


def test_fit_to_limit_does_not_add_content():
    text = "Tested login. Found bug. Reported it."
    result = fit_to_limit(text, limit=40, target=40)
    for word in ("Tested", "bug", "Reported"):
        assert word in result.text
