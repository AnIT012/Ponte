# Q: 通知の実際の送信手段（メール等）は指定されていないため、tick() は送った(持ち主, 会社名)のリストを返すのみとする。
# Q: 21:00は「時:分が21:00」を指すと解釈した（秒は無視）。同じ分に複数回 tick() を呼ぶと重複通知しうるが、重複防止の仕様がないため未対応。
# Q: due_soon の「3日以内」は now <= deadline <= now + 3日 と解釈した（過ぎた締切は対象外）。
# Q: extract_deadline は複数候補がある場合や年をまたぐ可能性がある表現は None とし、単一の "M/D(曜)? H:MM" 形式のみ確実に抽出する。
# Q: move で to が不正な文字列（4状態以外）の場合も ValueError とする。
# Q: passed/failed 確定後に同じ状態への再遷移（例: failed->failed, passed->passed）はエラーにしないものとした。
# Q: submitted からの draft への逆行など、定義された順序に反する遷移は全てエラーとする。

import re
import threading
import uuid
from datetime import datetime, timedelta

_STATUSES = ("draft", "submitted", "passed", "failed")

_ALLOWED_TRANSITIONS = {
    "draft": {"submitted"},
    "submitted": {"passed", "failed"},
    "passed": {"failed", "passed"},
    "failed": {"passed", "failed"},
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
        self._apps = {}  # id -> dict(user, company, deadline(datetime), status)
        self._order = []  # ids in add order
        self._lock = threading.Lock()
        self._app_locks = {}  # id -> Lock
        self._notified = set()  # (id, minute-key) to avoid duplicate notify within same tick call chain

    def set_now(self, now: datetime) -> None:
        with self._lock:
            self._now = now

    def add(self, user: str, company: str, deadline: str) -> str:
        dt = self._parse_deadline(deadline, self._now.year)
        app_id = str(uuid.uuid4())
        with self._lock:
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

    def apps(self, user: str) -> list:
        with self._lock:
            ids = list(self._order)
            snapshot = {i: dict(self._apps[i]) for i in ids if self._apps[i]["user"] == user}
        result = []
        for i in ids:
            if i in snapshot:
                a = snapshot[i]
                result.append({
                    "id": a["id"],
                    "company": a["company"],
                    "deadline": self._format_deadline(a["deadline"]),
                    "status": a["status"],
                })
        return result

    def due_soon(self, user: str) -> list:
        with self._lock:
            now = self._now
            candidates = [dict(a) for a in self._apps.values() if a["user"] == user]
        limit = now + timedelta(days=3)
        result = [
            a for a in candidates
            if a["status"] == "draft" and now <= a["deadline"] <= limit
        ]
        result.sort(key=lambda a: a["deadline"])
        return [
            {
                "id": a["id"],
                "company": a["company"],
                "deadline": self._format_deadline(a["deadline"]),
                "status": a["status"],
            }
            for a in result
        ]

    def tick(self) -> list:
        with self._lock:
            now = self._now
            if now.hour != 21 or now.minute != 0:
                return []
            all_apps = [dict(a) for a in self._apps.values()]

        minute_key = now.strftime("%Y-%m-%d %H:%M")
        limit = now + timedelta(days=3)
        due = [
            a for a in all_apps
            if a["status"] == "draft" and now <= a["deadline"] <= limit
        ]
        due.sort(key=lambda a: (a["user"], a["deadline"]))

        notified = []
        with self._lock:
            for a in due:
                key = (a["id"], minute_key)
                if key in self._notified:
                    continue
                self._notified.add(key)
                notified.append((a["user"], a["company"]))
        return notified

    def move(self, user: str, app_id: str, to: str) -> None:
        if to not in _STATUSES:
            raise ValueError(f"invalid status: {to}")

        lock = None
        with self._lock:
            app = self._apps.get(app_id)
            if app is None or app["user"] != user:
                raise ValueError("no such application for this user")
            lock = self._app_locks[app_id]

        with lock:
            with self._lock:
                app = self._apps.get(app_id)
                if app is None or app["user"] != user:
                    raise ValueError("no such application for this user")
                current = app["status"]
                if to == current and current in ("passed", "failed"):
                    return
                allowed = _ALLOWED_TRANSITIONS.get(current, set())
                if to not in allowed:
                    raise ValueError(f"invalid transition from {current} to {to}")
                if current == "passed" and to == "passed":
                    return
                if current == "failed" and to == "passed":
                    # failed takes priority; stay failed, not an error
                    return
                app["status"] = to

    def color(self, status: str) -> str:
        return _COLORS.get(status, "gray")

    def extract_deadline(self, mail: str) -> str:
        # Find all "M/D optional(weekday) H:MM" occurrences
        pattern = re.compile(
            r"(?<!\d)(\d{1,2})/(\d{1,2})(?:\([月火水木金土日]\))?\s*(\d{1,2}):(\d{2})(?!\d)"
        )
        matches = pattern.findall(mail)
        if len(matches) != 1:
            return None

        month_s, day_s, hour_s, minute_s = matches[0]
        try:
            month = int(month_s)
            day = int(day_s)
            hour = int(hour_s)
            minute = int(minute_s)
        except ValueError:
            return None

        if not (1 <= month <= 12):
            return None
        if not (1 <= day <= 31):
            return None
        if not (0 <= hour <= 23):
            return None
        if not (0 <= minute <= 59):
            return None

        try:
            datetime(2000, month, day, hour, minute)
        except ValueError:
            return None

        return f"{month}/{day} {hour}:{minute:02d}"

    @staticmethod
    def _parse_deadline(deadline: str, year: int) -> datetime:
        m = re.match(r"^\s*(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})\s*$", deadline)
        if not m:
            raise ValueError(f"invalid deadline format: {deadline}")
        month, day, hour, minute = (int(x) for x in m.groups())
        return datetime(year, month, day, hour, minute)

    @staticmethod
    def _format_deadline(dt: datetime) -> str:
        return f"{dt.month}/{dt.day} {dt.hour}:{dt.minute:02d}"
