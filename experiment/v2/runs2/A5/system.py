# Q: 「駄目な状態遷移」以外に submitted->draft のような逆行や draft/submitted 以外への
#     不正な to 値が来た場合も ValueError としている（要件に明記なしのため推測）。
# Q: due_soon の「3日以内」の起点は set_now/コンストラクタで渡された now の「日」を基準に、
#    now から3日後の日付の23:59までとした（例: 9/21 21:00 -> 9/24 23:59 まで含む）。
# Q: tick() は21:00ちょうど（分も0）のときのみ通知するものとした。
# Q: tick() が返す順序は、応募が追加された順（id発行順）とした。
# Q: extract_deadline は、本文中に候補となる日時表現が複数（重複除く）見つかった場合は
#    曖昧とみなし None を返すこととした。
# Q: 年をまたぐ締切（deadline の年は常に「今の年」固定、add() 時点の now.year を使用）。
# Q: color() の「それ以外」は未知の status 文字列が渡された場合を想定し gray とした。

import re
import threading
import uuid
from datetime import datetime, timedelta

_STATUS_ORDER = {
    "draft": 0,
    "submitted": 1,
    "passed": 2,
    "failed": 2,
}

_COLORS = {
    "draft": "orange",
    "submitted": "blue",
    "passed": "green",
    "failed": "gray",
}

_FULLWIDTH_MAP = {}
for i in range(10):
    _FULLWIDTH_MAP[ord("0") + i + 0xFEE0] = str(i)
_FULLWIDTH_MAP[ord("／") ] = "/"
_FULLWIDTH_MAP[ord("：")] = ":"
_FULLWIDTH_MAP[ord("（")] = "("
_FULLWIDTH_MAP[ord("）")] = ")"
_FULLWIDTH_MAP[ord("【")] = "["
_FULLWIDTH_MAP[ord("】")] = "]"

_DEADLINE_RE = re.compile(
    r"(\d{1,2})\s*/\s*(\d{1,2})\s*(?:\([^)]{0,4}\))?\s*(\d{1,2})\s*:\s*(\d{2})"
)


class System:
    def __init__(self, now: datetime):
        self._now = now
        self._apps = {}          # id -> dict
        self._order = []         # list of ids, in add() order
        self._global_lock = threading.Lock()
        self._app_locks = {}     # id -> Lock

    def set_now(self, now: datetime) -> None:
        self._now = now

    def _get_app_lock(self, app_id):
        with self._global_lock:
            lock = self._app_locks.get(app_id)
            if lock is None:
                lock = threading.Lock()
                self._app_locks[app_id] = lock
            return lock

    def add(self, user: str, company: str, deadline: str) -> str:
        app_id = uuid.uuid4().hex
        dt = self._parse_deadline_str(deadline, self._now.year)
        record = {
            "id": app_id,
            "user": user,
            "company": company,
            "deadline": dt,
            "status": "draft",
        }
        with self._global_lock:
            self._apps[app_id] = record
            self._order.append(app_id)
            self._app_locks[app_id] = threading.Lock()
        return app_id

    @staticmethod
    def _parse_deadline_str(deadline: str, year: int) -> datetime:
        m = re.match(r"(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})", deadline.strip())
        if not m:
            raise ValueError(f"invalid deadline format: {deadline}")
        month, day, hour, minute = (int(x) for x in m.groups())
        return datetime(year, month, day, hour, minute)

    def _public(self, record: dict) -> dict:
        return {
            "id": record["id"],
            "company": record["company"],
            "deadline": f'{record["deadline"].month}/{record["deadline"].day} '
                        f'{record["deadline"].hour}:{record["deadline"].minute:02d}',
            "status": record["status"],
        }

    def apps(self, user: str) -> list:
        with self._global_lock:
            ids = list(self._order)
        result = []
        for app_id in ids:
            rec = self._apps.get(app_id)
            if rec is not None and rec["user"] == user:
                result.append(self._public(rec))
        return result

    def _due_soon_records(self, user: str):
        end_of_range = (self._now + timedelta(days=3)).replace(
            hour=23, minute=59, second=0, microsecond=0
        )
        with self._global_lock:
            ids = list(self._order)
        due = []
        for app_id in ids:
            rec = self._apps.get(app_id)
            if rec is None or rec["user"] != user:
                continue
            if rec["status"] != "draft":
                continue
            if rec["deadline"] < self._now:
                continue
            if rec["deadline"] > end_of_range:
                continue
            due.append(rec)
        due.sort(key=lambda r: r["deadline"])
        return due

    def due_soon(self, user: str) -> list:
        return [self._public(r) for r in self._due_soon_records(user)]

    def tick(self) -> list:
        if self._now.hour != 21 or self._now.minute != 0:
            return []
        end_of_range = (self._now + timedelta(days=3)).replace(
            hour=23, minute=59, second=0, microsecond=0
        )
        with self._global_lock:
            ids = list(self._order)
        notified = []
        for app_id in ids:
            rec = self._apps.get(app_id)
            if rec is None:
                continue
            if rec["status"] != "draft":
                continue
            if rec["deadline"] < self._now:
                continue
            if rec["deadline"] > end_of_range:
                continue
            notified.append((rec["user"], rec["company"]))
        return notified

    def move(self, user: str, app_id: str, to: str) -> None:
        if to not in _STATUS_ORDER:
            raise ValueError(f"invalid target status: {to}")

        lock = self._get_app_lock(app_id)
        with lock:
            rec = self._apps.get(app_id)
            if rec is None or rec["user"] != user:
                raise ValueError("no such application for this user")

            current = rec["status"]

            if current == "passed" and to == "failed":
                rec["status"] = "failed"
                return
            if current == "failed" and to == "passed":
                return

            allowed_next = {
                "draft": {"submitted"},
                "submitted": {"passed", "failed"},
                "passed": set(),
                "failed": set(),
            }
            if to not in allowed_next.get(current, set()):
                raise ValueError(f"cannot move from {current} to {to}")

            rec["status"] = to

    def color(self, status: str) -> str:
        return _COLORS.get(status, "gray")

    def extract_deadline(self, mail: str):
        normalized = mail.translate(_FULLWIDTH_MAP)
        matches = _DEADLINE_RE.findall(normalized)
        if not matches:
            return None

        seen = set()
        candidates = []
        for month, day, hour, minute in matches:
            try:
                mi, di, hi, mni = int(month), int(day), int(hour), int(minute)
            except ValueError:
                continue
            if not (1 <= mi <= 12 and 1 <= di <= 31 and 0 <= hi <= 23 and 0 <= mni <= 59):
                continue
            key = (mi, di, hi, mni)
            if key not in seen:
                seen.add(key)
                candidates.append(key)

        if len(candidates) != 1:
            return None

        mi, di, hi, mni = candidates[0]
        return f"{mi}/{di} {hi}:{mni:02d}"
