# Q: 通知の送信手段は指定がないため、送った (owner, company) を返すことだけを実装とする（実際の送信は行わない）。
# Q: due_soon の3日以内は「now <= deadline <= now+3日」とし、締切が既に過ぎたものは含めないと解釈した。
# Q: tick() は「今が21:00ちょうど（秒は0扱い）」のときに発火するとし、1分の窓を許容せず時:分が21:00と完全一致する場合に発火するものとした。
# Q: 同じ21:00の1分間に複数回 tick() が呼ばれた場合の重複通知防止は要件に無いため、実装しない（毎回 due_soon を再評価して返す）。
# Q: extract_deadline の年推測禁止・複数候補ありの場合は None、という仕様に沿い、月/日 時:分 のパターンが本文中に複数個ある場合は None を返す。
# Q: move で to が不正な文字列（未知の状態名）の場合も ValueError とする。
# Q: color の「それ以外」は未知の status 文字列が来た場合 gray を返す、とした。

import re
import threading
import uuid
from datetime import datetime, timedelta

_STATUSES = ("draft", "submitted", "passed", "failed")

_ALLOWED_TRANSITIONS = {
    "draft": {"submitted"},
    "submitted": {"passed", "failed"},
    "passed": {"failed"},   # failed overrides passed
    "failed": {"failed"},   # passed after failed is a no-op, not an error (handled specially)
}

_COLORS = {
    "draft": "orange",
    "submitted": "blue",
    "passed": "green",
    "failed": "gray",
}


class System:
    def __init__(self, now: datetime):
        self._now = now
        self._apps = {}          # id -> dict
        self._order = []         # id list in insertion order
        self._lock = threading.Lock()
        self._app_locks = {}     # id -> threading.Lock

    def set_now(self, now: datetime) -> None:
        with self._lock:
            self._now = now

    def _get_app_lock(self, app_id: str) -> threading.Lock:
        with self._lock:
            lk = self._app_locks.get(app_id)
            if lk is None:
                lk = threading.Lock()
                self._app_locks[app_id] = lk
            return lk

    def add(self, user: str, company: str, deadline: str) -> str:
        with self._lock:
            year = self._now.year
            dt = self._parse_deadline(deadline, year)
            app_id = uuid.uuid4().hex
            self._apps[app_id] = {
                "id": app_id,
                "user": user,
                "company": company,
                "deadline_str": deadline,
                "deadline_dt": dt,
                "status": "draft",
            }
            self._order.append(app_id)
            return app_id

    @staticmethod
    def _parse_deadline(deadline: str, year: int) -> datetime:
        m = re.match(r"^(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})$", deadline.strip())
        if not m:
            raise ValueError(f"invalid deadline format: {deadline}")
        month, day, hour, minute = (int(x) for x in m.groups())
        return datetime(year, month, day, hour, minute)

    def apps(self, user: str) -> list:
        with self._lock:
            result = []
            for app_id in self._order:
                a = self._apps[app_id]
                if a["user"] == user:
                    result.append({
                        "id": a["id"],
                        "company": a["company"],
                        "deadline": a["deadline_str"],
                        "status": a["status"],
                    })
            return result

    def due_soon(self, user: str) -> list:
        with self._lock:
            now = self._now
            limit = now + timedelta(days=3)
            items = []
            for app_id in self._order:
                a = self._apps[app_id]
                if a["user"] != user:
                    continue
                if a["status"] != "draft":
                    continue
                if now <= a["deadline_dt"] <= limit:
                    items.append(a)
            items.sort(key=lambda a: a["deadline_dt"])
            return [
                {
                    "id": a["id"],
                    "company": a["company"],
                    "deadline": a["deadline_str"],
                    "status": a["status"],
                }
                for a in items
            ]

    def tick(self) -> list:
        with self._lock:
            now = self._now
            if not (now.hour == 21 and now.minute == 0):
                return []
            limit = now + timedelta(days=3)
            notified = []
            for app_id in self._order:
                a = self._apps[app_id]
                if a["status"] != "draft":
                    continue
                if now <= a["deadline_dt"] <= limit:
                    notified.append((a["user"], a["company"]))
            return notified

    def move(self, user: str, app_id: str, to: str) -> None:
        if to not in _STATUSES:
            raise ValueError(f"unknown status: {to}")

        lock = self._get_app_lock(app_id)
        with lock:
            with self._lock:
                a = self._apps.get(app_id)
                if a is None or a["user"] != user:
                    raise ValueError("no such application for this user")
                current = a["status"]

            if current == to:
                # passed -> passed / failed -> failed etc: no explicit rule; treat as no-op only
                # for the failed-after-passed special case below; otherwise disallow same-state jump
                if current == "failed" and to == "failed":
                    return
                raise ValueError(f"invalid transition: {current} -> {to}")

            # special rule: failed takes priority; passed after failed is a no-op, not error
            if current == "failed" and to == "passed":
                with self._lock:
                    return  # stay failed, no error

            allowed = _ALLOWED_TRANSITIONS.get(current, set())
            if to not in allowed:
                raise ValueError(f"invalid transition: {current} -> {to}")

            with self._lock:
                a["status"] = to

    def color(self, status: str) -> str:
        return _COLORS.get(status, "gray")

    def extract_deadline(self, mail: str) -> str:
        pattern = re.compile(r"(\d{1,2})/(\d{1,2})[^\d]{0,10}?(\d{1,2}):(\d{2})")
        matches = pattern.findall(mail)
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
