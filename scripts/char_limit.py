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
# The portal limit is an allowance, not a target. Preferred ranges describe a
# concise field; anything above the preferred maximum is still acceptable up
# to ``DEFAULT_LIMIT`` and is labelled "Detailed" rather than "too short" or
# "almost full".
PREFERRED_DAILY_MIN = 500
PREFERRED_DAILY_MAX = 1200
DETAILED_DAILY_MAX = 1500
PREFERRED_WEEKLY_MIN = 800
PREFERRED_WEEKLY_MAX = 1500

CONCISE = "Concise"
DETAILED = "Detailed"
OVER_LIMIT = "Over limit"


def length_band(count: int, preferred_max: int, limit: int = DEFAULT_LIMIT) -> str:
    """Classify a measured field: Concise, Detailed, or Over limit.

    * ``Concise`` - within the preferred range (short is good, not a problem).
    * ``Detailed`` - above the preferred range but inside the hard limit.
      Allowed, especially on a busy or technically complex day.
    * ``Over limit`` - above the portal maximum; would be rejected.
    """
    if count > limit:
        return OVER_LIMIT
    if count <= preferred_max:
        return CONCISE
    return DETAILED


def band_summary(
    count: int,
    preferred_min: int,
    preferred_max: int,
    limit: int = DEFAULT_LIMIT,
) -> str:
    """Short label for a rendered counter, e.g. ``Concise``."""
    band = length_band(count, preferred_max, limit)
    if band == CONCISE and count < preferred_min:
        return f"{CONCISE}, below preferred {preferred_min}-{preferred_max}"
    if band == CONCISE:
        return f"{CONCISE}, preferred {preferred_min}-{preferred_max}"
    if band == DETAILED:
        return f"{DETAILED}, above preferred {preferred_max} but within {limit}"
    return f"{OVER_LIMIT} ({limit} max)"


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
# A list marker ("6.", "A)", "12.") is not a sentence boundary.
_LIST_MARKER = re.compile(r"(?m)^([ \t]*(?:\d{1,3}|[A-Za-z])[.)])[ \t]+")
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


def split_block_sentences(block: str) -> list[str]:
    """Split a block into sentences without breaking list markers.

    ``6. Test case status`` must stay one sentence; a naive split on the
    period turns it into a bare ``6.`` plus an orphaned remainder.
    """
    markers: list[str] = []

    def _protect(match: re.Match[str]) -> str:
        markers.append(match.group(1))
        return f"\x00{len(markers) - 1}\x00 "

    protected = _LIST_MARKER.sub(_protect, block)
    parts = [p for p in _SENTENCE_END.split(protected) if p.strip()]
    out = []
    for part in parts:
        restored = re.sub(
            r"\x00(\d+)\x00", lambda m: markers[int(m.group(1))], part
        )
        out.append(restored.strip())
    return out


def _sentence_score(sentence: str) -> int:
    """Importance of a sentence: identifiers, numbers and length.

    Numbers count: a sentence carrying measured figures ("364 rows, 205 Done")
    is the payload a supervisor reads, so it is dropped last.
    """
    score = float(len(_TECH_SIGNAL.findall(sentence)) * 3)
    score += 2 * len(re.findall(r"\d", sentence))
    if re.search(
        r"\b(PASS|FAIL|BLOCKED|SKIPPED|NOT RUN|Outcome|Result|Total|Net)\b", sentence
    ):
        score += 4
    # Fractional length term breaks score ties, so the drop order stays stable
    # instead of falling back to document position.
    score += len(sentence) / 80.0
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

    # 1. Trim sentences first. Every block keeps its opening sentence, so no
    #    section, numbered item or finding disappears - only its supporting
    #    detail is thinned. Lowest-signal sentences go first.
    blocks = [b for b in work.split("\n\n") if b.strip()]
    sentences: list[list[str]] = [
        split_block_sentences(block) for block in blocks
    ]
    dropped_sentences = 0
    while True:
        flat = "\n\n".join(" ".join(parts) for parts in sentences if parts)
        if count_chars(flat) <= budget:
            break
        # Drop by worst value density first: the sentence that gives up the
        # most characters per unit of importance. Long, low-signal sentences
        # go before short, fact-dense ones.
        candidates = [
            (_sentence_score(s) / max(len(s), 40), -bi, -si)
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
        dropped_sentences += 1
    if dropped_sentences:
        result.dropped_sentences = dropped_sentences
        work = "\n\n".join(" ".join(parts) for parts in sentences if parts)
        result.text, result.final_count = work, count_chars(work)
        if result.final_count <= budget:
            result.changed = True
            result.notes.append(
                "condensed sentence by sentence; every section kept"
            )
            return result

    # 2. Still over: drop whole low-value blocks, keeping the leading blocks
    #    and the first block under each heading.
    blocks = [b for b in work.split("\n\n") if b.strip()]
    all_blocks = list(blocks)
    keep = set(range(min(keep_head_blocks, len(blocks))))
    heading_like = re.compile(
        r"^(?:#{1,6}\s|[A-Z][.)]|\d+[.)]|\w+\s+[\u2014-]\s|"
        r"(?:Workstream|Section|Part|Block|Phase|Appendix)\b)",
        re.I,
    )
    protected = {
        i for i in range(1, len(blocks)) if heading_like.match(blocks[i - 1].strip())
    }
    order = sorted(
        (i for i in range(len(blocks)) if i not in keep),
        key=lambda i: (_block_score(blocks[i]) - (10 if i in protected else 0), -i),
    )
    dropped: set[int] = set()
    for i in order:
        current = "\n\n".join(
            b for j, b in enumerate(blocks) if j not in dropped
        )
        if count_chars(current) <= budget:
            break
        dropped.add(i)
    if dropped:
        # 2b. Refill: put back any dropped block that still fits, in source
        # order, so the field carries as much real content as the limit allows.
        current_idx = [j for j in range(len(all_blocks)) if j not in dropped]
        for j in range(len(all_blocks)):
            if j not in dropped:
                continue
            trial = sorted(current_idx + [j])
            if count_chars("\n\n".join(all_blocks[k] for k in trial)) <= budget:
                dropped.discard(j)
                current_idx = trial
        result.dropped_blocks = len(dropped)
        work = "\n\n".join(all_blocks[k] for k in sorted(current_idx))
        result.text, result.final_count = work, count_chars(work)
        if result.final_count <= budget:
            result.changed = True
            result.notes.append(
                "removed lowest-value blocks"
                if result.dropped_blocks
                else "reflowed blocks to fit the limit"
            )
            return result

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
