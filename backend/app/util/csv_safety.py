"""CSV/spreadsheet formula-injection neutralization (M1-R1 blocking #2).

A cell whose text starts with `=`, `+`, `-`, or `@` is interpreted as a
formula by Excel/Google Sheets/LibreOffice when the file is opened there --
letting an attacker plant e.g. `=HYPERLINK(...)` or a DDE payload in a name/
email/phone field that later gets written back out to a CSV (or pasted
into a spreadsheet from an admin's report). Neutralize on the way *in*
(CSV import) by prefixing a leading single quote, which spreadsheet
applications render as "force text" and strip from display, while leaving
the value intact for programmatic (non-spreadsheet) consumers.

`escape_for_csv_export` is the same neutralization applied on the way *out*
-- kept as a separate, explicitly-named entry point so a CSV/XLSX export
endpoint (03-API-SPEC.md `GET /exports/items.csv|xlsx`, not part of this
milestone) has a ready-made, already-tested helper to call on every cell it
writes, even for values that reached the DB via a path other than CSV
import (e.g. typed directly into the admin UI).
"""

from __future__ import annotations

_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_cell(value: str | None) -> str | None:
    """Neutralize a formula-injection payload in a single CSV cell.

    `None` and the empty string pass through unchanged (nothing to
    neutralize); everything else gets a leading `'` inserted if its first
    character is one spreadsheet apps treat as a formula trigger.
    """
    if not value:
        return value
    if value[0] in _DANGEROUS_PREFIXES:
        return "'" + value
    return value


# Exported under a second name for the export path (see module docstring) --
# the implementation is identical, but the name documents *why* it's being
# called at each call site.
escape_for_csv_export = sanitize_csv_cell
