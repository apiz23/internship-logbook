"""Character-limit counting and validation for university submissions.

University portals count *every* character in a field: letters, spaces,
punctuation and line breaks. This module is the single place that decides
how long a field is and whether it is still within its limit, so the
generator, the CLI and the tests all agree.

Counting rules
--------------
* ``len(text)`` after newline normalisation to ``\\n`` - so a line break
  costs one character, an em dash costs one character (not two bytes).
* Trailing/leading whitespace that the portal would also store is counted.
  Do not strip before counting; strip before *rendering* if you must.

Nothing here guesses: ``check_limit`` measures the string it is given.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

DEFAULT_LIMIT = 4000
# Safety margin used when a long field has to be written: aim for the
# 3,500-3,800 band rather than sitting on the 4,000 edge.
TARGET_MIN = 3500
TARGET_MAX = 3800


def normalise_newlines(text: str) -> str:
    """Return ``text`` with CRLF/CR line endings normalised to ``\\n``."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def count_chars(text: str) -> int:
    """Count characters the way the portal does, newlines included.

    Unicode is counted per code point (Python's ``len``), which matches a
    text input that stores the field as text rather than bytes.
    """
    return len(normalise_newlines(text or ""))


def count_chars_crlf(text: str) -> int:
    """Count characters if the field is submitted with CRLF line endings."""
    return len((text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n"))


@dataclass(frozen=True)
class CharCount:
    """Result of measuring one field against its limit."""

    text: str
    limit: int = DEFAULT_LIMIT
    count: int = 0
    remaining: int = 0
    over_by: int = 0
    within_limit: bool = True

    def summary(self) -> str:
        if self.within_limit:
            return f"{self.count} / {self.limit} characters ({self.remaining} remaining)"
        return (
            f"{self.count} / {self.limit} characters "
            f"(OVER by {self.over_by} characters)"
        )


def check_limit(text: str, limit: int = DEFAULT_LIMIT) -> CharCount:
    """Measure ``text`` and compare it to ``limit``."""
    clean = normalise_newlines(text or "")
    n = len(clean)
    over = max(0, n - limit)
    return CharCount(
        text=clean,
        limit=limit,
        count=n,
        remaining=limit - n,
        over_by=over,
        within_limit=n <= limit,
    )


# ---------------------------------------------------------------------------
# Shortening without losing the important parts
# ---------------------------------------------------------------------------

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\"'`])")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
_BULLET = re.compile(r"^\s{0,3}(?:[-*+]|\d+[.)])\s+")
_NESTED = re.compile(r"^\s{2,}(?:[-*+]|\d+[.)])\s+")
_TECH_SIGNAL = re.compile(
    r"(\bBUG-\d+|\bTC-?\d+|\b[A-Z]{2,}-\d+|\d+(?:\.\d+)?%|\bhttps?://|\b[A-Z][a-z]+[A-Z]\w+)"
)


def _block_score(block: str) -> int:
    """Heuristic importance of a block, for deciding what to drop first.

    Higher = keep. Deterministic and content-based: numbers, identifiers,
    URLs and named technical tokens are the parts a supervisor reads.
    """
    score = len(_TECH_SIGNAL.findall(block)) * 3
    score += len(re.findall(r"\d", block)) // 4
    score += 2 if _BULLET.match(block) or _HEADING.match(block) else 0
    score += 1 if "status" in block.lower() else 0
    return score


def _sentence_score(sentence: str) -> int:
    score = len(_TECH_SIGNAL.findall(sentence)) * 2
    score += len(sentence) // 200
    return score


def _tidy(text: str) -> str:
    text = normalise_newlines(text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@dataclass
class FitResult:
    """Outcome of shortening a field to fit its limit."""

    text: str
    limit: int
    original_count: int
    final_count: int
    changed: bool = False
    dropped_blocks: int = 0
    dropped_sentences: int = 0
    hard_truncated: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def within_limit(self) -> bool:
        return self.final_count <= self.limit

    def summary(self) -> str:
        if not self.changed:
            return f"{self.final_count} / {self.limit} characters (unchanged)"
        bits = [
            f"shortened {self.original_count} -> {self.final_count} / {self.limit} characters",
        ]
        if self.dropped_blocks:
            bits.append(f"{self.dropped_blocks} block(s) removed")
        if self.dropped_sentences:
            bits.append(f"{self.dropped_sentences} sentence(s) removed")
        if self.hard_truncated:
            bits.append("hard-truncated at a word boundary")
        return ", ".join(bits)


def fit_to_limit(
    text: str,
    limit: int = DEFAULT_LIMIT,
    target: int | None = None,
    keep_head_blocks: int = 1,
) -> FitResult:
    """Shorten ``text`` until it fits ``limit`` (and ``target`` if given).

    Only ever *removes* content - it never adds or rewrites a claim - so a
    shortened field cannot introduce information the source did not hold.
    Removal order: low-value whole blocks first, then low-value sentences,
    then a word-boundary cut as a last resort.
    """
    original = count_chars(text)
    budget = limit if target is None else min(limit, target)
    work = _tidy(text)
    result = FitResult(
        text=work,
        limit=limit,
        original_count=original,
        final_count=count_chars(work),
    )

    if result.final_count <= budget:
        return result

    # 1. Drop whole blocks, lowest score first, keeping the leading blocks.
    blocks = [b for b in work.split("\n\n") if b.strip()]
    all_blocks = list(blocks)
    keep = set(range(min(keep_head_blocks, len(blocks))))
    order = sorted(
        (i for i in range(len(blocks)) if i not in keep),
        key=lambda i: (_block_score(blocks[i]), -i),
    )
    dropped: set[int] = set()
    for i in order:
        if count_chars("\n\n".join(b for j, b in enumerate(blocks) if j not in dropped)) <= budget:
            break
        dropped.add(i)
    if dropped:
        # 1b. Refill: put back any dropped block that still fits, in source
        # order, so the field carries as much real content as the limit allows
        # instead of stopping at the first coarse cut.
        current = [j for j in range(len(all_blocks)) if j not in dropped]
        for j in range(len(all_blocks)):
            if j not in dropped:
                continue
            trial = sorted(current + [j])
            if count_chars("\n\n".join(all_blocks[k] for k in trial)) <= budget:
                dropped.discard(j)
                current = trial
        result.dropped_blocks = len(dropped)
        work = "\n\n".join(all_blocks[k] for k in sorted(current))
        result.text, result.final_count = work, count_chars(work)
        if result.final_count <= budget:
            result.changed = True
            result.notes.append(
                "removed lowest-value blocks"
                if result.dropped_blocks
                else "reflowed blocks to fit the limit"
            )
            return result

    # 2. Drop sentences, lowest score first, never the first sentence of a block.
    sentences: list[list[str]] = []
    for block in blocks:
        parts = [p for p in _SENTENCE_END.split(block) if p.strip()]
        sentences.append(parts)
    dropped_s = 0
    while True:
        flat = "\n\n".join(" ".join(parts) for parts in sentences if parts)
        if count_chars(flat) <= budget:
            break
        candidates = [
            (len(_TECH_SIGNAL.findall(s)), -bi, -si)
            for bi, parts in enumerate(sentences)
            for si, s in enumerate(parts)
            if si > 0 and len(parts) > 1
        ]
        if not candidates:
            break
        _, nbi, nsi = min(candidates)
        sentences[-nbi] = [
            s for idx, s in enumerate(sentences[-nbi]) if idx != -nsi
        ]
        dropped_s += 1
    if dropped_s:
        result.dropped_sentences = dropped_s
        work = "\n\n".join(" ".join(parts) for parts in sentences if parts)
        result.text, result.final_count = work, count_chars(work)

    # 3. Last resort: cut on a word boundary and mark it.
    if result.final_count > budget:
        cut = result.text[:budget]
        cut = cut[: cut.rfind(" ")] if " " in cut else cut
        result.text = cut.rstrip()
        result.final_count = count_chars(result.text)
        result.hard_truncated = True
        result.notes.append("hard cut at word boundary to satisfy the limit")

    result.changed = result.text != _tidy(text)
    if result.changed and not result.notes:
        result.notes.append("condensed to fit the character limit")
    return result


def validate_many(
    fields: Sequence[tuple[str, str]], limit: int = DEFAULT_LIMIT
) -> list[CharCount]:
    """Measure several ``(name, text)`` pairs against the same limit."""
    return [check_limit(text, limit) for _, text in fields]


def summarise_many(counts: Iterable[CharCount], limit: int = DEFAULT_LIMIT) -> str:
    lines = []
    for c in counts:
        lines.append(f"- {c.summary()}")
    return "\n".join(lines)
