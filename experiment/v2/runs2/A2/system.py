# Q: 通知の実送信手段は指定がないため、実際の送信は行わず (持ち主, 会社名) を返すのみとした。
# Q: tick() で複数ユーザーの通知順は "応募を追加した順" とした（要件に明記なし）。
# Q: due_soon の「3日以内」の下限は「今より前（既に過ぎた締切）は除く」とし、下限チェックは now <= deadline とした。
# Q: extract_deadline は、本文中に月/日 時:分の形が「ちょうど1つ」見つかった場合のみ返し、0件または2件以上は None（自信がない扱い）とした。
# Q: 年をまたぐ締切（例: 12月に来年1月分の応募を追加）は考慮せず、常に now.year を使う。
# Q: add() の deadline 文字列は "M/D H:MM" 形式のみを受け付け、パースできない場合は ValueError とした。

from __future__ import annotations

import re
import threading
from datetime import datetime, timedelta, time as dtime


class System:
    def __init__(self, now: datetime):
        self._now = now
        self._apps: dict[str, dict] = {}
        self._order: list[str] = []
        self._next_id = 1
        self._global_lock = threading.Lock()
        self._app_locks: dict[str, threading.Lock] = {}
        self._last_tick_key = None  # avoid double notify within same minute if tick() called repeatedly

    # ---------- helpers ----------

    def _get_lock(self, app_id: str) -> threading.Lock:
        with self._global_lock:
            lock = self._app_locks.get(app_id)
            if lock is None:
                lock = threading.Lock()
                self._app_locks[app_id] = lock
            return lock

    def _parse_deadline(self, deadline: str) -> datetime:
        m = re.match(r"^\s*(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})\s*$", deadline)
        if not m:
            raise ValueError(f"invalid deadline format: {deadline!r}")
        month, day, hour, minute = (int(x) for x in m.groups())
        return datetime(self._now.year, month, day, hour, minute)

    @staticmethod
    def _format_deadline(d: datetime) -> str:
        return f"{d.month}/{d.day} {d.hour:02d}:{d.minute:02d}"

    # ---------- public API ----------

    def set_now(self, now: datetime) -> None:
        self._now = now

    def add(self, user: str, company: str, deadline: str) -> str:
        dt = self._parse_deadline(deadline)
        with self._global_lock:
            app_id = f"app-{self._next_id}"
            self._next_id += 1
            self._apps[app_id] = {
                "id": app_id,
                "user": user,
                "company": company,
                "deadline": dt,
                "status": "draft",
            }
            self._order.append(app_id)
            self._app_locks[app_id] = threading.Lock()
        return app_id

    def apps(self, user: str) -> list[dict]:
        result = []
        for app_id in self._order:
            app = self._apps.get(app_id)
            if app is None or app["user"] != user:
                continue
            result.append(
                {
                    "id": app["id"],
                    "company": app["company"],
                    "deadline": self._format_deadline(app["deadline"]),
                    "status": app["status"],
                }
            )
        return result

    def due_soon(self, user: str) -> list[dict]:
        now = self._now
        cutoff_date = now.date() + timedelta(days=3)
        cutoff = datetime.combine(cutoff_date, dtime(23, 59))
        candidates = []
        for app_id in self._order:
            app = self._apps.get(app_id)
            if app is None or app["user"] != user:
                continue
            if app["status"] != "draft":
                continue
            deadline = app["deadline"]
            if deadline < now:
                continue
            if deadline > cutoff:
                continue
            candidates.append(app)
        candidates.sort(key=lambda a: a["deadline"])
        return [
            {
                "id": a["id"],
                "company": a["company"],
                "deadline": self._format_deadline(a["deadline"]),
                "status": a["status"],
            }
            for a in candidates
        ]

    def tick(self) -> list[tuple[str, str]]:
        now = self._now
        if now.hour != 21 or now.minute != 0:
            return []

        notified: list[tuple[str, str]] = []
        cutoff_date = now.date() + timedelta(days=3)
        cutoff = datetime.combine(cutoff_date, dtime(23, 59))
        for app_id in self._order:
            app = self._apps.get(app_id)
            if app is None:
                continue
            if app["status"] != "draft":
                continue
            deadline = app["deadline"]
            if deadline < now or deadline > cutoff:
                continue
            notified.append((app["user"], app["company"]))
        return notified

    def move(self, user: str, app_id: str, to: str) -> None:
        if to not in ("draft", "submitted", "passed", "failed"):
            raise ValueError(f"invalid target status: {to!r}")

        lock = self._get_lock(app_id)
        with lock:
            app = self._apps.get(app_id)
            if app is None or app["user"] != user:
                raise ValueError("no such application for this user")

            current = app["status"]

            if current == "draft" and to == "submitted":
                app["status"] = "submitted"
                return
            if current == "submitted" and to in ("passed", "failed"):
                app["status"] = to
                return
            if current == "passed" and to == "failed":
                # failed が優先されるため上書きする（エラーにしない）
                app["status"] = "failed"
                return
            if current == "failed" and to == "passed":
                # failed のまま維持する（エラーにしない）
                return
            if current == to:
                # 同じ状態への遷移は許容する
                return

            raise ValueError(
                f"invalid transition from {current!r} to {to!r}"
            )

    def color(self, status: str) -> str:
        mapping = {
            "draft": "orange",
            "submitted": "blue",
            "passed": "green",
            "failed": "gray",
        }
        return mapping.get(status, "gray")

    def extract_deadline(self, mail: str) -> str | None:
        normalized = self._normalize(mail)
        pattern = re.compile(
            r"(\d{1,2})/(\d{1,2})(?:\([^)]{0,3}\))?\s*(\d{1,2}):(\d{2})"
        )
        matches = pattern.findall(normalized)
        if len(matches) != 1:
            return None
        month, day, hour, minute = matches[0]
        try:
            month_i, day_i, hour_i, minute_i = int(month), int(day), int(hour), int(minute)
        except ValueError:
            return None
        if not (1 <= month_i <= 12 and 1 <= day_i <= 31 and 0 <= hour_i <= 23 and 0 <= minute_i <= 59):
            return None
        return f"{month_i}/{day_i} {hour_i:02d}:{minute_i:02d}"

    @staticmethod
    def _normalize(text: str) -> str:
        # 全角数字 -> 半角数字
        table = {ord("０") + i: str(i) for i in range(10)}
        # 全角記号 -> 半角記号
        table[ord("／")] = "/"
        table[ord("：")] = ":"
        table[ord("（")] = "("
        table[ord("）")] = ")"
        table[ord("　")] = " "
        return text.translate(table)
