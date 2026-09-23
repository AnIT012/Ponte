# Q: 通知の送信手段（メール等）は指定がないため、tick() は (owner, company) のリストを返すのみとし、実際の送信は行わない。
# Q: 「21時ちょうど」の判定は、時=21かつ分=0とし、秒以下は無視する。
# Q: 同じ21:00の呼び出しで複数回 tick() が呼ばれた場合の重複通知抑止は要件に無いため、毎回対象を再計算して返す（重複抑止なし）。
# Q: move() で to に不正な文字列（未知の状態名）が来た場合も ValueError とする。
# Q: extract_deadline は本文中に複数の締切候補（曖昧な複数マッチ）がある場合は None を返す。
# Q: extract_deadline で見つかった月/日が実在しない日付（例 2/30）の場合はNoneを返す。
# Q: id はグローバルに一意な文字列（連番）とする。
# Q: 締切の年は「今の年」を使うとの指定通りに解釈する。年をまたぐ判定は行わない。

import re
import threading
from datetime import datetime, timedelta

_STATUS_ORDER = ["draft", "submitted", "passed", "failed"]
_ALLOWED_TRANSITIONS = {
    "draft": {"submitted"},
    "submitted": {"passed", "failed"},
    "passed": {"failed"},
    "failed": set(),
}

_COLORS = {
    "draft": "orange",
    "submitted": "blue",
    "passed": "green",
    "failed": "gray",
}

_ZEN2HAN_DIGITS = str.maketrans({
    "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
    "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
    "／": "/", "：": ":", "（": "(", "）": ")",
})


def _normalize(text: str) -> str:
    return text.translate(_ZEN2HAN_DIGITS)


_DEADLINE_RE = re.compile(
    r"(?P<month>\d{1,2})/(?P<day>\d{1,2})(?:\([^)]*\))?\s*(?P<hour>\d{1,2}):(?P<minute>\d{2})"
)


class System:
    def __init__(self, now: datetime):
        self._now = now
        self._apps = {}  # id -> dict(owner, company, deadline(datetime), status)
        self._order = []  # ids in insertion order
        self._next_id = 1
        self._global_lock = threading.Lock()
        self._app_locks = {}

    def set_now(self, now: datetime) -> None:
        self._now = now

    def _get_app_lock(self, app_id: str) -> threading.Lock:
        with self._global_lock:
            lock = self._app_locks.get(app_id)
            if lock is None:
                lock = threading.Lock()
                self._app_locks[app_id] = lock
            return lock

    def add(self, user: str, company: str, deadline: str) -> str:
        deadline_dt = self._parse_deadline(deadline)
        with self._global_lock:
            app_id = str(self._next_id)
            self._next_id += 1
            self._apps[app_id] = {
                "id": app_id,
                "owner": user,
                "company": company,
                "deadline": deadline_dt,
                "status": "draft",
            }
            self._order.append(app_id)
            self._app_locks[app_id] = threading.Lock()
        return app_id

    def _parse_deadline(self, deadline: str) -> datetime:
        s = _normalize(deadline)
        m = re.match(r"(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})", s)
        if not m:
            raise ValueError(f"invalid deadline format: {deadline}")
        month, day, hour, minute = (int(x) for x in m.groups())
        return datetime(self._now.year, month, day, hour, minute)

    def apps(self, user: str) -> list[dict]:
        result = []
        for app_id in self._order:
            app = self._apps.get(app_id)
            if app is None or app["owner"] != user:
                continue
            result.append(self._to_public(app))
        return result

    def _to_public(self, app: dict) -> dict:
        return {
            "id": app["id"],
            "company": app["company"],
            "deadline": app["deadline"].strftime("%-m/%-d %H:%M") if hasattr(app["deadline"], "strftime") else app["deadline"],
            "status": app["status"],
        }

    def due_soon(self, user: str) -> list[dict]:
        limit = self._due_soon_limit()
        candidates = []
        for app_id in self._order:
            app = self._apps.get(app_id)
            if app is None or app["owner"] != user:
                continue
            if app["status"] != "draft":
                continue
            if app["deadline"] < self._now:
                continue
            if app["deadline"] <= limit:
                candidates.append(app)
        candidates.sort(key=lambda a: a["deadline"])
        return [self._to_public(a) for a in candidates]

    def _due_soon_limit(self) -> datetime:
        target_date = (self._now + timedelta(days=3)).date()
        return datetime(target_date.year, target_date.month, target_date.day, 23, 59)

    def tick(self) -> list[tuple[str, str]]:
        if self._now.hour != 21 or self._now.minute != 0:
            return []
        limit = self._due_soon_limit()
        candidates = []
        for app_id in self._order:
            app = self._apps.get(app_id)
            if app is None:
                continue
            if app["status"] != "draft":
                continue
            if app["deadline"] < self._now:
                continue
            if app["deadline"] <= limit:
                candidates.append(app)
        candidates.sort(key=lambda a: a["deadline"])
        return [(a["owner"], a["company"]) for a in candidates]

    def move(self, user: str, app_id: str, to: str) -> None:
        if to not in _STATUS_ORDER:
            raise ValueError(f"invalid status: {to}")
        lock = self._get_app_lock(app_id)
        with lock:
            app = self._apps.get(app_id)
            if app is None or app["owner"] != user:
                raise ValueError("app not found or not owned by user")
            current = app["status"]
            if current == "passed" and to == "failed":
                app["status"] = "failed"
                return
            if current == "failed" and to == "passed":
                return
            if to not in _ALLOWED_TRANSITIONS.get(current, set()):
                raise ValueError(f"invalid transition from {current} to {to}")
            app["status"] = to

    def color(self, status: str) -> str:
        return _COLORS.get(status, "gray")

    def extract_deadline(self, mail: str) -> str | None:
        text = _normalize(mail)
        matches = list(_DEADLINE_RE.finditer(text))
        if len(matches) != 1:
            return None
        m = matches[0]
        month = int(m.group("month"))
        day = int(m.group("day"))
        hour = int(m.group("hour"))
        minute = int(m.group("minute"))
        if not (1 <= month <= 12):
            return None
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        try:
            datetime(2000, month, day)
        except ValueError:
            return None
        return f"{month}/{day} {hour:02d}:{minute:02d}"
