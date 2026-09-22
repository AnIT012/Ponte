"""値の読み書き（日時・期間など）。実行エンジンとテストで共有する。"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

_MD = re.compile(r"^(\d{1,2})/(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?$")
_FULL = re.compile(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?$")


def parse_time(text: str, year: int) -> datetime:
    """"9/24 23:59"（年なし）は year の年として読む。"2026/9/24 23:59" はそのまま。"""
    t = text.strip().strip('"')
    m = _FULL.match(t)
    if m:
        y, mo, d, h, mi = m.groups()
        return datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0))
    m = _MD.match(t)
    if m:
        mo, d, h, mi = m.groups()
        return datetime(year, int(mo), int(d), int(h or 0), int(mi or 0))
    raise ValueError(f"日時が読めません: '{text}'")


def format_monthday(dt: datetime) -> str:
    return f"{dt.month}/{dt.day} {dt.hour}:{dt.minute:02d}"


_DUR = re.compile(r"^(\d+)\s+(seconds?|minutes?|hours?|days?|weeks?)$")


def within(value: datetime, now: datetime, dur: str) -> bool:
    """now <= value <= 期限。days / weeks は暦日（N日後の終わりまで）。"""
    m = _DUR.match(dur.strip())
    if not m:
        raise ValueError(f"期間が読めません: '{dur}'")
    n, unit = int(m.group(1)), m.group(2).rstrip("s")
    if unit in ("day", "week"):
        end_day = now + timedelta(days=n * (7 if unit == "week" else 1))
        end = end_day.replace(hour=23, minute=59, second=59, microsecond=999999)
    else:
        end = now + {"second": timedelta(seconds=n), "minute": timedelta(minutes=n), "hour": timedelta(hours=n)}[unit]
    return now <= value <= end


def unquote(v: str) -> str:
    v = v.strip()
    return v[1:-1] if len(v) >= 2 and v[0] == '"' and v[-1] == '"' else v


_KV = re.compile(r'(\w+)\s+("[^"]*"|[^,]+)')


def parse_record(text: str) -> tuple[str, dict[str, str]]:
    """`Application(company "Osaka Gas", status draft)` → ("Application", {...})"""
    m = re.match(r"^(\w+)\((.*)\)$", text.strip())
    if not m:
        raise ValueError(f"`箱名(項目 値, ...)` で書きます: '{text}'")
    fields = {k: unquote(v) for k, v in _KV.findall(m.group(2))}
    return m.group(1), fields
