"""Messages in English or Japanese.

The source code keeps its messages in Japanese. When the output language is English,
each Japanese message is translated on its way out, using the catalog in `i18n_en.json`.

- Keys are message templates taken from the source (`{}` marks each value put into the message).
- Values are the English templates. `{}` takes the values in order; `{0}` / `{1}` can reorder them.
- A value of `null` means "not a message" (a pattern or keyword list that happens to contain Japanese).

`tests/test_i18n.py` extracts every Japanese string from the source and fails if one has no entry,
so a new message cannot be added without its English version.

Which language: `--lang` → `PONTE_LANG` → the system locale (`LANG` / `LC_ALL` starting with `ja` → Japanese) → English.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
from functools import lru_cache

JP = re.compile(r"[぀-ヿ㐀-鿿＀-￯]")
_lang: str | None = None


def set_lang(lang: str | None) -> None:
    global _lang
    _lang = lang if lang in ("ja", "en") else None


def lang() -> str:
    if _lang:
        return _lang
    env = os.environ.get("PONTE_LANG", "").lower()
    if env in ("ja", "en"):
        return env
    loc = (os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or "").lower()
    return "ja" if loc.startswith("ja") else "en"


@lru_cache(maxsize=1)
def _patterns() -> list[tuple[re.Pattern, str, int]]:
    path = os.path.join(os.path.dirname(__file__), "i18n_en.json")
    try:
        catalog = json.load(open(path, encoding="utf-8"))
    except FileNotFoundError:
        return []
    out = []
    for ja, en in catalog.items():
        if not en or len(JP.findall(ja)) < 2:        # not a message, or too short to find safely
            continue
        parts = ja.replace("{{", "\0").replace("}}", "\1").split("{}")
        lit = [re.escape(p.replace("\0", "{").replace("\1", "}")) for p in parts]
        rx = lit[0]
        for i, p in enumerate(lit[1:]):
            last = i == len(lit) - 2
            rx += ("(.+)" if last and not p else "(.+?)") + p
        out.append((re.compile(rx), en, len(ja)))
    out.sort(key=lambda x: -x[2])                   # longest first, so a whole message wins over its pieces
    return out


def _fill(en: str, values: list[str]) -> str:
    if re.search(r"\{\d+\}", en):
        return re.sub(r"\{(\d+)\}", lambda m: values[int(m.group(1))] if int(m.group(1)) < len(values) else "", en)
    it = iter(values)
    return re.sub(r"(?<!\{)\{\}(?!\})", lambda m: next(it, ""), en).replace("{{", "{").replace("}}", "}")


def tr(text: str, depth: int = 0) -> str:
    """Japanese → English when the output language is English. Anything not in the catalog stays as it is."""
    if lang() == "ja" or not text or not JP.search(text) or depth > 3:
        return text
    for rx, en, _ in _patterns():
        m = rx.search(text)
        if m:
            vals = [tr(g, depth + 1) for g in m.groups()]
            text = text[:m.start()] + _fill(en, vals) + text[m.end():]
            if not JP.search(text):
                break
    return text


class _Writer(io.TextIOBase):
    """Wraps stdout / stderr and translates each line as it is written."""

    def __init__(self, raw):
        self.raw, self.buf = raw, ""

    def write(self, s: str) -> int:
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            self.raw.write(tr(line) + "\n")
        return len(s)

    def flush(self) -> None:
        if self.buf:
            self.raw.write(tr(self.buf))
            self.buf = ""
        self.raw.flush()

    def isatty(self) -> bool:
        return self.raw.isatty()

    @property
    def encoding(self):
        return getattr(self.raw, "encoding", "utf-8")


def install() -> None:
    """Translate everything the CLI prints (only when the output language is English)."""
    if lang() == "en" and not isinstance(sys.stdout, _Writer):
        sys.stdout = _Writer(sys.stdout)
        sys.stderr = _Writer(sys.stderr)
