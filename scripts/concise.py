"""Concise, extractive summarisation for university submission fields.

The portal limit (4,000 characters) is a *maximum allowance*, not a target.
A supervisor reads a short, accurate account; padding the field with
administrative detail makes it worse, not better.

Rules this module follows
------------------------
* **Extractive only.** Every sentence kept already exists in the source
  record. Nothing is rewritten, inferred or invented, so a summary cannot
  claim work the logbook does not document.
* **Noise goes first.** URLs, timestamps, file paths, hashes, exhaustive
  test-identifier lists and `Key: value` metadata dumps are dropped before
  any content sentence is.
* **Findings stay.** Defect identifiers, outcomes (passed, failed, blocked,
  reproduced), measured counts and blocker wording score highest, so they
  survive when the budget is tight.
* **Deterministic.** Same input, same output: no randomness, no clock.

The caller chooses the budget (see ``university_profile``): a preferred
range for a normal field and a slightly larger ceiling for a genuinely busy
day. The hard portal limit is enforced by ``char_limit.fit_to_limit`` after
this module returns, and every result is measured again there.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_WS = re.compile(r"\s+")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\"'`])")
_LIST_MARKER = re.compile(r"(?m)^([ \t]*(?:\d{1,3}|[A-Za-z])[.)])[ \t]+")

_URL = re.compile(r"https?://|www\.", re.I)
_TIMESTAMP = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")
_HEX_ID = re.compile(r"\b[0-9a-f]{16,}\b", re.I)
_PATH = re.compile(
    r"(?:[\w.-]+/){2,}[\w.-]+\.\w{2,4}\b"
    r"|\b[\w-]+\.(?:md|png|jpe?g|pdf|csv|json|xlsx|docx|txt|mp4|mov)\b",
    re.I,
)
_FIELD_PAIR = re.compile(r"\b[A-Z][A-Za-z /()]{1,24}:\s")
_TC_ID = re.compile(r"\bTC-?\d+\b")
_BUG_ID = re.compile(r"\bBUG-\d+\b")
_PLACEHOLDER = re.compile(r"\b(?:TBD|TBC|XXX+|placeholder|to be confirmed)\b", re.I)
_BOILERPLATE = re.compile(
    r"no blocking issue|continue with the planned|nothing further|as planned|"
    r"no issue (?:was|is) (?:found|identified)",
    re.I,
)
_OUTCOME = re.compile(
    r"\b(?:completed|confirmed|verified|fixed|resolved|closed|approved|deferred|"
    r"reported|logged|raised|recorded|updated|implemented|delivered|"
    r"passed|failed|blocked|skipped|reproduced|prevented)\b",
    re.I,
)
_FINDING = re.compile(
    r"\b(?:found|identified|discovered|observed|revealed|root cause|"
    r"cannot|unable|fails?|failure|regression|mismatch|inconsistent|"
    r"not rendered|did not|does not)\b",
    re.I,
)
_MEASURE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:%|rows?|cases?|hours?|days?|files?|items?)\b", re.I)
_REPORT_VERB = re.compile(
    r"^(?:Reviewed|Tested|Executed|Ran|Reported|Verified|Recorded|Updated|Created|"
    r"Added|Removed|Investigated|Compared|Confirmed|Documented|Wrote|Checked|"
    r"Queried|Audited|Classified|Established|Pulled|Filled|Rebuilt|Validated|"
    r"Supplied|Clarified|Identified|Monitored|Tracked|Prepared|Reconciled|Mapped|"
    r"Logged|Raised|Fixed|Found|Noted|Read|Built|Converted|Rendered|Extracted|"
    r"Analysed|Analyzed|Inspected|Deployed|Merged|Escalated|Reviewed|Set|Used|"
    r"Measured|Captured|Reproduced|Retested|Reran|Completed|Continued|Started|"
    r"Finished|Kept|Collected|Gathered|Applied|Moved|Replaced|Cleaned|Split|"
    r"Tested|Screened|Triage[dt]|Blocked|Deferred|Skipped|Passed|Failed)\b"
)
_PROJECT = re.compile(
    r"\b(?:O'?Zone|O'?Care|OTalk|OChat|Kiwi Import|Hermes|Creator Research)\b", re.I
)
_HEADING_ONLY = re.compile(r"^[A-Z0-9][^\n]{0,80}$")
_DASH_SPLIT = re.compile(r"\s+[\u2014\u2013-]\s+")
_META = re.compile(
    r"predates today|see .{0,20}below|recorded date|reviewed today|"
    r"as noted above|this test case'?s|refer to (?:case|the)|"
    r"per the .{0,20}checklist|for reference|corresponds to (?:the |an? )?"
    r"(?:existing )?(?:checklist )?case|read-only review|no edits (?:were )?made|"
    r"this step",
    re.I,
)
_ID_TOKEN = re.compile(r"\b[A-Z]{2,}-\d{1,4}\b")
_VERB = re.compile(
    r"\b(?:is|are|was|were|be|been|being|has|have|had|does|did|do|"
    r"tested|updated|reviewed|reported|recorded|verified|found|removed|ran|"
    r"wrote|added|created|confirmed|logged|identified|checked|prepared|"
    r"investigated|executed|ran|used|made|took|gave|set|kept|started)\b"
    # Past-tense reporting verbs beyond the list above ("moved", "resolved").
    r"|\b\w{3,}ed\b",
    re.I,
)


def normalise(text: str) -> str:
    return _WS.sub(" ", (text or "").replace("\r\n", "\n").replace("\r", "\n")).strip()


def _heading_only(text: str) -> bool:
    """True for a short section title that carries no statement."""
    words = text.split()
    if len(words) > 8:
        return False
    if text.endswith((".", "!", "?")):
        return False
    return not _VERB.search(text)


def clean_line(line: str) -> str:
    """Turn one Markdown/notes line into plain content.

    Markers, section-title prefixes (``Label — content``) and inline
    administrative detail are removed; nothing is invented.
    """
    text = (line or "").strip()
    if not text or text.startswith(("```", "|---", "|")):
        return ""
    text = re.sub(r"^#{1,6}\s*", "", text)
    text = re.sub(r"^[-*+\u2022]\s+", "", text)
    text = re.sub(r"^\d{1,3}[.)]\s+", "", text)
    text = re.sub(r"^[A-Za-z][.)]\s+", "", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    # Administrative detail adds length, not information.
    text = re.sub(r"\(?https?://[^\s)]+\)?", "", text)
    text = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", "", text)
    text = re.sub(
        r"\(?[\w./-]*[\w-]+\.(?:md|png|jpe?g|pdf|csv|json|xlsx|docx|txt)\b\)?",
        "",
        text,
    )
    text = re.sub(r"\s{2,}", " ", text).strip(" :")
    # Removing a clock time can leave a hole ("created between and UTC"), so
    # such a line is dropped rather than rendered.
    if re.search(r"\bbetween\s+and\b|\bfrom\s+to\b|\bat\s+on\b|\bon\s+\.", text):
        return ""
    parts = _DASH_SPLIT.split(text)
    if len(parts) >= 3:
        # Several dashes: only a run of short labels is a heading prefix.
        # Otherwise the dashes are punctuation inside a real sentence.
        if all(len(part.split()) <= 5 for part in parts[:-1]):
            text = parts[-1]
        else:
            text = ", ".join(part.strip(" ,;:") for part in parts)
    elif len(parts) == 2:
        left, right = parts
        # A left side made only of identifiers ("815 (A1), 820 (A6)") is a
        # label for the bullets under it, not prose: keeping it renders
        # "815 (A1), 820 (A6) — upload pick and form" as a broken clause.
        if re.fullmatch(r"[\s\dA-Za-z().,\-/–—]*\d{3}[\s\dA-Za-z().,\-/–—]*", left.strip()) and not re.search(r"[a-z]{4,}", left):
            text = right
        # "Heading — content" only: both sides must look like a label and a
        # statement, so "Bug Tracker — Test Run Log" is not cut in half.
        elif (
            len(left.split()) <= 6
            and not left.rstrip().endswith((".", "!", "?"))
            and len(right) > 40
            and "," not in left
            and not _BUG_ID.search(left)
        ):
            text = right
    return text.strip(" :")


def clean_text(text: str) -> str:
    """Turn notes into prose blocks: one paragraph per blank-line block.

    Logbook records are hard-wrapped at the margin and mix headings, bullets
    and continuation lines. Cleaning line by line turns a wrapped sentence
    into fragments, so each block is cleaned, its heading lines dropped, and
    its remaining lines joined back into whole sentences.
    """
    blocks = re.split(r"\n\s*\n", (text or "").replace("\r\n", "\n"))
    out: list[str] = []
    for block in blocks:
        parts: list[tuple[str, bool]] = []
        for raw in block.splitlines():
            marked = raw.strip()
            # Markdown headings and stand-alone bold titles are section names,
            # not content: keeping them merges a title into the next sentence.
            if marked.startswith("#"):
                continue
            if re.fullmatch(r"\*\*[^*]+\*\*", marked):
                continue
            line = clean_line(raw)
            if not line or _heading_only(line):
                continue
            is_bullet = bool(re.match(r"^[-*+\u2022]\s+|^\d{1,3}[.)]\s+", marked))
            parts.append((line, is_bullet))
        # A block that is nothing but a short title carries no content. Inside
        # a multi-line block the same shape is a hard-wrapped line of real
        # prose, so it must be kept — dropping those emptied whole days.
        if len(parts) == 1:
            only = parts[0][0]
            if (
                len(only.split()) <= 12
                and not only.endswith((".", "!", "?", ";", ":"))
                and not parts[0][1]
            ):
                continue
        if parts:
            joined = ""
            for part, is_bullet in parts:
                if not joined:
                    joined = part
                elif joined.rstrip()[-1] in ".!?:;,":
                    joined = joined.rstrip() + " " + part
                elif is_bullet:
                    # A list item starts its own statement.
                    joined = joined.rstrip() + ". " + part
                else:
                    # Records are hard-wrapped at the margin, so a line that
                    # does not end in punctuation is a wrap, not a sentence
                    # boundary. Inserting a full stop there invented a break
                    # mid-phrase ("remaining O'Zone. staging cases") and every
                    # later sentence filter then read the wreckage as noise.
                    joined = joined.rstrip() + " " + part
            joined = re.sub(r"\s+", " ", joined).strip()
            if joined:
                out.append(joined)
    return "\n\n".join(out)


def split_sentences(text: str) -> list[str]:
    """Split prose into sentences, keeping ``1.`` style markers attached."""
    markers: list[str] = []

    def _protect(match: re.Match[str]) -> str:
        markers.append(match.group(1))
        return f"\x00{len(markers) - 1}\x00 "

    protected = _LIST_MARKER.sub(_protect, normalise(text))
    out: list[str] = []
    for part in _SENTENCE_END.split(protected):
        if not part.strip():
            continue
        restored = re.sub(r"\x00(\d+)\x00", lambda m: markers[int(m.group(1))], part)
        restored = restored.strip()
        # A bare list marker (``3.``) carries nothing on its own.
        if restored and not re.fullmatch(r"\d{1,3}[.)]", restored):
            out.append(restored)
    return out


def _dedupe(sentences: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for sentence in sentences:
        key = normalise(sentence).lower().strip(" .;:-")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(sentence)
    return out


def is_administrative_noise(sentence: str) -> bool:
    """True when a sentence is portal/bookkeeping detail rather than work.

    Timestamps, URLs, file paths, hashes, identifier dumps and multi-field
    metadata lines tell a supervisor nothing about the internship, and they
    are the first things a tight budget should spend.
    """
    if _URL.search(sentence) or _TIMESTAMP.search(sentence):
        return True
    if _HEX_ID.search(sentence) or _PATH.search(sentence):
        return True
    if len(_FIELD_PAIR.findall(sentence)) >= 2:
        return True
    if len(_TC_ID.findall(sentence)) >= 2:
        return True
    if _PLACEHOLDER.search(sentence):
        return True
    if _BOILERPLATE.search(sentence) or _META.search(sentence):
        return True
    # An exhaustive identifier list belongs in the tracker, not the field.
    # Four or five IDs can still be a real finding ("these cases failed"), so
    # only a long run of identifiers counts as a dump.
    if len(_ID_TOKEN.findall(sentence)) >= 6:
        return True
    return False


def sentence_score(sentence: str) -> float:
    """Importance of one sentence for a supervisor-facing summary."""
    score = 0.0
    if _BUG_ID.search(sentence):
        score += 3.0
    if _OUTCOME.search(sentence):
        score += 2.5
    if _FINDING.search(sentence):
        score += 2.0
    if _MEASURE.search(sentence):
        score += 1.5
    if _PROJECT.search(sentence):
        score += 1.0
    # A reporting sentence that opens with its verb ("Tested ...", "Reported
    # ...") stands alone, so it is preferred over one that depends on the
    # sentence before it.
    if _REPORT_VERB.match(sentence):
        score += 4.0
    length = len(sentence)
    if 60 <= length <= 300:
        score += 1.0
    elif length > 300:
        score -= 1.5
    elif length < 60:
        score -= 1.0
    ids = len(_ID_TOKEN.findall(sentence))
    if ids >= 3:
        score -= 1.5 * (ids - 2)
    if is_administrative_noise(sentence):
        score -= 6.0
    return score


def _looks_like_fragment(sentence: str) -> bool:
    """True for wreckage from a heading split, not a usable sentence.

    Raw notes contain bullet fragments, quoted code and half-sentences; a
    field must read as prose, so anything that cannot stand alone is dropped
    rather than stitched into the task detail.
    """
    text = sentence.strip()
    if not text or len(text.split()) < 5:
        return True
    if text.endswith((":", ",")):
        return True
    if text.count('"') % 2 or text.count("(") != text.count(")"):
        return True
    # A left-over "Heading - content" join reads as two half-sentences.
    if _DASH_SPLIT.search(text):
        return True
    if text[0] in ")]}\"'(/":
        return True
    first = text.split(" ", 1)[0]
    if text[0].islower() and not any(c.isupper() for c in first[1:]):
        return True
    # A lowercase continuation after a full stop means the splitter caught a
    # wrap, not a sentence boundary ("... from Adam. confirming that ...").
    if re.search(r"[.!?]\s+[a-z]", text):
        return True
    if re.search(r"\.(?:php|js|py|ts|md):\d+", text):
        return True
    # "Test case statistics, Extracted the breakdown" - a title and its body
    # joined by a comma, which reads as two half-sentences.
    if re.search(r"^[A-Z][^,]{0,45},\s+[A-Z][a-z]+(?:ed|s)\b", text):
        return True
    # Removing a URL or a path can leave a hole ("filed as ;"). A sentence
    # with a gap reads as a broken record, so it is dropped.
    if re.search(r"\(\s*\)|\s;|;\s*[.;]|,\s*\.|\b(?:as|in|at|from|to)\s*[;,.](?:\s|$)", text):
        return True
    # A dangling preposition or article means the source sentence was cut.
    if re.search(
        r"\b(?:at|in|on|of|to|for|from|with|and|or|the|a|an|by|as|into)$", text.rstrip(" .;:")
    ):
        return True
    return False


def summarise_sequential(
    text: str,
    *,
    min_chars: int = 500,
    max_chars: int = 1200,
    busy_max_chars: int = 1500,
    outcome_sentences: int = 2,
) -> ConciseResult:
    """Take the record in its own order, stopping at a sentence boundary.

    The written record already opens with what was worked on and continues
    in a logical order, so keeping that order reads far better than ranking
    sentences out of context. Administrative and broken sentences are
    skipped, the field stops once the preferred budget is reached, and a
    couple of high-value findings from later in the record are added when
    they still fit inside the busy-day allowance.
    """
    clean = clean_text(text)
    sentences = [
        s
        for block in clean.split("\n\n")
        for s in split_sentences(block)
        if s.strip() and not _looks_like_fragment(s) and not is_administrative_noise(s)
    ]
    if not sentences:
        return ConciseResult(text="", budget=max_chars)

    chosen: list[int] = []
    used = 0
    for i, sentence in enumerate(sentences):
        cost = len(sentence) + 1
        if used + cost > max_chars:
            break
        chosen.append(i)
        used += cost

    # Later findings (defects, measured results) are worth one or two slots
    # even when the opening sentences already fill the budget.
    if outcome_sentences:
        rest = sorted(
            (i for i in range(len(sentences)) if i not in chosen),
            key=lambda i: (-sentence_score(sentences[i]), i),
        )
        for i in rest[: outcome_sentences * 3]:
            if outcome_sentences <= 0:
                break
            cost = len(sentences[i]) + 1
            if used + cost <= busy_max_chars and sentence_score(sentences[i]) >= 4:
                chosen.append(i)
                used += cost
                outcome_sentences -= 1

    ordered = [sentences[i] for i in sorted(chosen)]
    body = _paragraphs(ordered, 3)
    return ConciseResult(
        text=body,
        selected=len(ordered),
        dropped=max(0, len(sentences) - len(ordered)),
        budget=busy_max_chars if used > max_chars else max_chars,
        busy=used > max_chars,
    )


@dataclass
class ConciseResult:
    """A summary built only from source sentences."""

    text: str
    selected: int = 0
    dropped: int = 0
    budget: int = 0
    busy: bool = False

    @property
    def chars(self) -> int:
        return len(self.text)


def _paragraphs(sentences: list[str], per_paragraph: int = 3) -> str:
    chunks = [
        " ".join(sentences[i : i + per_paragraph])
        for i in range(0, len(sentences), per_paragraph)
    ]
    return "\n\n".join(chunk for chunk in chunks if chunk.strip())


def summarise(
    text: str,
    *,
    min_chars: int = 500,
    max_chars: int = 1200,
    busy_max_chars: int | None = 1500,
    opener_sentences: int = 1,
    per_paragraph: int = 3,
    busy_threshold: int = 12,
) -> ConciseResult:
    """Pick the most useful source sentences within a character budget.

    The first sentence is always kept: it states what the day (or week) was
    about, and dropping it would leave the field starting mid-thought.
    Everything else is chosen by score, then emitted in source order so the
    result still reads as a record of the day rather than a ranked list.

    When a lot of material was left out (a genuinely busy day), the budget
    rises to ``busy_max_chars``; it never exceeds it.
    """
    sentences = _dedupe(
        [
            s
            for s in split_sentences(clean_text(text))
            if s.strip() and not _looks_like_fragment(s)
        ]
    )
    if not sentences:
        return ConciseResult(text="", budget=max_chars)

    opener = min(max(0, opener_sentences), len(sentences))
    chosen_idx = list(range(opener))
    used = sum(len(sentences[i]) + 1 for i in chosen_idx)

    # Prefer standalone reporting sentences, then by score; dependent
    # sentences are only used to reach the preferred floor.
    order = sorted(
        (i for i in range(opener, len(sentences))),
        key=lambda i: (
            0 if _REPORT_VERB.match(sentences[i]) else 1,
            -sentence_score(sentences[i]),
            i,
        ),
    )

    def add(i: int, budget: int) -> bool:
        nonlocal used
        cost = len(sentences[i]) + 1
        if used + cost > budget:
            return False
        chosen_idx.append(i)
        used += cost
        return True

    for i in order:
        if is_administrative_noise(sentences[i]) or not _REPORT_VERB.match(sentences[i]):
            continue
        add(i, max_chars)

    busy = False
    dropped = len(sentences) - len(chosen_idx)
    if busy_max_chars and busy_max_chars > max_chars and dropped >= busy_threshold:
        for i in order:
            if (
                i in chosen_idx
                or is_administrative_noise(sentences[i])
                or not _REPORT_VERB.match(sentences[i])
            ):
                continue
            add(i, busy_max_chars)
            if used > max_chars:
                busy = True
        dropped = len(sentences) - len(chosen_idx)

    # Never pad with noise, but do reach the preferred floor with real
    # content when the record holds enough of it.
    if used < min_chars:
        for i in range(len(sentences)):
            if i in chosen_idx or is_administrative_noise(sentences[i]):
                continue
            if used >= min_chars:
                break
            if add(i, max_chars if not busy else (busy_max_chars or max_chars)):
                used = sum(len(sentences[j]) + 1 for j in chosen_idx)

    ordered = [sentences[i] for i in sorted(chosen_idx)]
    body = _paragraphs(ordered, per_paragraph)
    return ConciseResult(
        text=body,
        selected=len(ordered),
        dropped=max(0, len(sentences) - len(ordered)),
        budget=busy_max_chars if busy and busy_max_chars else max_chars,
        busy=busy,
    )


def summarise_blocks(
    blocks: list[str],
    *,
    min_chars: int = 800,
    max_chars: int = 1500,
    lead_sentences: int = 1,
    per_paragraph: int = 2,
) -> ConciseResult:
    """Summarise several paragraphs, keeping each one's opening sentence.

    A week report is written paragraph by paragraph (focus, progress,
    defects, constraints). Dropping a whole paragraph loses a theme, so the
    first sentence of every paragraph is kept and only the supporting
    sentences compete for the remaining budget.
    """
    cleaned: list[list[str]] = []
    for block in blocks:
        sentences = [
            s
            for s in split_sentences(clean_text(block))
            if s.strip() and not _looks_like_fragment(s)
        ]
        if sentences:
            cleaned.append(sentences)
    if not cleaned:
        return ConciseResult(text="", budget=max_chars)

    chosen: list[set[int]] = [
        set(range(min(lead_sentences, len(parts)))) for parts in cleaned
    ]
    used = sum(
        len(cleaned[bi][si]) + 1 for bi, idx in enumerate(chosen) for si in idx
    )
    candidates = sorted(
        (
            (sentence_score(cleaned[bi][si]), bi, si)
            for bi, parts in enumerate(cleaned)
            for si in range(len(parts))
            if si not in chosen[bi] and not is_administrative_noise(parts[si])
        ),
        key=lambda item: (-item[0], item[1], item[2]),
    )
    for score, bi, si in candidates:
        cost = len(cleaned[bi][si]) + 1
        if used + cost > max_chars:
            continue
        chosen[bi].add(si)
        used += cost

    if used < min_chars:
        for bi, parts in enumerate(cleaned):
            for si in range(len(parts)):
                if used >= min_chars:
                    break
                if si in chosen[bi]:
                    continue
                cost = len(parts[si]) + 1
                if used + cost > max_chars:
                    continue
                chosen[bi].add(si)
                used += cost

    out_blocks: list[str] = []
    for bi, parts in enumerate(cleaned):
        kept = [parts[si] for si in sorted(chosen[bi])]
        if kept:
            out_blocks.append(_paragraphs(kept, per_paragraph))
    total_selected = sum(len(idx) for idx in chosen)
    total_all = sum(len(parts) for parts in cleaned)
    return ConciseResult(
        text="\n\n".join(out_blocks),
        selected=total_selected,
        dropped=max(0, total_all - total_selected),
        budget=max_chars,
    )


def drop_heading_only_blocks(text: str, max_words: int = 8) -> str:
    """Remove blocks that are only a section title (no verb, no content).

    ``A. Tracker review`` or ``Wednesday — upload checks`` on their own add
    length without information; the sentences under them carry the work.
    """
    blocks = [b.strip() for b in (text or "").split("\n\n") if b.strip()]
    kept: list[str] = []
    for block in blocks:
        flat = normalise(block)
        if (
            len(flat.split()) <= max_words
            and not flat.endswith((".", "!", "?"))
            and _HEADING_ONLY.match(flat)
            and not _BUG_ID.search(flat)
        ):
            continue
        kept.append(block)
    return "\n\n".join(kept)


def collect_bug_ids(text: str) -> list[str]:
    """Unique defect identifiers in source order (for grouped mentions)."""
    seen: list[str] = []
    for match in _BUG_ID.findall(text or ""):
        if match not in seen:
            seen.append(match)
    return seen
