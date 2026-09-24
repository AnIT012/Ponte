"""Required parts of each heading, for editors.

After a heading line such as `rule Finish`, an editor may put in the names of the parts that heading
cannot do without, and nothing else: no placeholder text, no optional parts. The writer fills in the rest.
tests/test_skeleton.py proves each part listed here is really required (leaving it out is an error),
so the list cannot drift from the checker.
"""
from __future__ import annotations

REQUIRED: dict[str, list[str]] = {
    "rule": ["when", "do"],
    "action": ["in", "out", "example", "example", "else"],
    "list": ["of"],
    "match": ["else ->"],
    "model": ["learn", "using", "require", "else"],
}


def lines_after(heading_line: str) -> list[str]:
    """`rule Finish` → ["  when ", "  do "]. Anything else → []."""
    word = heading_line.split(None, 1)[0] if heading_line.strip() and not heading_line.startswith(" ") else ""
    return [f"  {p} " for p in REQUIRED.get(word, [])]


def snippet(word: str) -> str | None:
    """LSP snippet: `rule $1` and the required parts, each with an empty tab stop."""
    parts = REQUIRED.get(word)
    if parts is None:
        return None
    return "\n".join([f"{word} $1"] + [f"  {p} ${i + 2}" for i, p in enumerate(parts)])
