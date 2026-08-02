"""Delimiter detection, header detection, and row splitting for pasted/CSV tabular text."""

from __future__ import annotations

CANDIDATE_DELIMS = ["\t", "|", ";", ",", " "]


def split_line(line: str, delim: str) -> list[str]:
    """Splits a single line on a delimiter. Space delimiter collapses runs of
    whitespace (mimics space-aligned paste); all others split literally."""
    if delim == " ":
        return line.split()
    return [cell.strip() for cell in line.split(delim)]


def detect_delimiter(text: str) -> str:
    """Tries each candidate delimiter and picks whichever produces the most
    consistent, widest split across sample lines."""
    lines = [l for l in text.splitlines() if l.strip()][:20]
    if not lines:
        return ","

    best_delim = ","
    best_score = -1
    for delim in CANDIDATE_DELIMS:
        counts = [len(split_line(l, delim)) for l in lines]
        if all(c <= 1 for c in counts):
            continue  # this delimiter doesn't split anything -> not it
        first = counts[0]
        consistent = sum(1 for c in counts if c == first)
        score = first * consistent
        if score > best_score:
            best_score = score
            best_delim = delim
    return best_delim


def split_rows(text: str, delim: str) -> list[list[str]]:
    return [split_line(l, delim) for l in text.splitlines() if l.strip()]


def _looks_numeric(s: str) -> bool:
    s = s.strip()
    if not s:
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False


def detect_header(rows: list[list[str]]) -> bool:
    """Heuristic: if the header row breaks the numeric pattern of a column
    that's otherwise mostly numeric, and no numeric column contradicts that,
    row 0 is a header."""
    if len(rows) < 2:
        return False
    header_row = rows[0]
    ncols = len(header_row)
    body = rows[1:]
    body_total = len(body)
    if body_total == 0:
        return False

    votes_for = 0
    votes_against = 0
    for col in range(ncols):
        header_cell = header_row[col] if col < len(header_row) else ""
        body_numeric_count = sum(
            1 for r in body if col < len(r) and _looks_numeric(r[col])
        )
        body_mostly_numeric = body_numeric_count * 2 >= body_total
        if not body_mostly_numeric:
            continue
        if _looks_numeric(header_cell):
            votes_against += 1
        else:
            votes_for += 1

    return votes_for > 0 and votes_against == 0
