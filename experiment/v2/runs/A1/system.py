# Q: 「締切が近い」の3日以内は、境界(ちょうど3日後)を含むと解釈した。
# Q: 「今の時刻が21:00」は分単位で厳密一致(時=21,分=0)とし、同じ21:00に複数回tickを呼んだ場合、
#     すでに通知済みの応募は再通知しないこととした(重複通知防止のため)。
# Q: due_soon の対象は状態が draft のみとし、締切が過去(期限切れ)でも3日以内なら含めることとした
#     (要件に「過ぎたら除外」との記載がないため)。
# Q: move で to が現在の状態と同じ場合(例: passed→passed)はエラーとせず何もしないこととした。
# Q: extract_deadline は年をまたぐ判定はせず、単純に「M/D H:MM」形式の抽出のみ行う。
# Q: ユーザーIDは呼び出し側が渡す文字列をそのまま信頼する(認証は本システムの範囲外)。

import re
import threading
from datetime import datetime, timedelta

_STATUS_ORDER = {
    "draft": 0,
    "submitted": 1,
    "passed": 2,
    "failed": 2,
}

_ALLOWED_MOVES = {
    "draft": {"submitted"},
    "submitted": {"passed", "failed"},
    "passed": {"failed"},  # passed -> failed 上書き許可
    "failed": set(),  # failed からは動かせない(failed->passed は要件によりエラーにしない=無視)
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
        self._apps = {}  # id -> dict(user, company, deadline_dt, status)
        self._order = []  # id list in add order
        self._next_id = 1
        self._global_lock = threading.Lock()
        self._app_locks = {}  # id -> Lock
        self._notified_at = None  # (year, month, day, hour, minute) of last tick that notified

    def set_now(self, now: datetime) -> None:
        self._now = now

    def _parse_deadline(self, deadline: str) -> datetime:
        m = re.match(r"^(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})$", deadline.strip())
        if not m:
            raise ValueError("invalid deadline format")
        month, day, hour, minute = (int(x) for x in m.groups())
        year = self._now.year
        return datetime(year, month, day, hour, minute)

    def add(self, user: str, company: str, deadline: str) -> str:
        deadline_dt = self._parse_deadline(deadline)
        with self._global_lock:
            app_id = f"a{self._next_id}"
            self._next_id += 1
            self._apps[app_id] = {
                "id": app_id,
                "user": user,
                "company": company,
                "deadline_dt": deadline_dt,
                "status": "draft",
            }
            self._order.append(app_id)
            self._app_locks[app_id] = threading.Lock()
        return app_id

    def _fmt_deadline(self, dt: datetime) -> str:
        return f"{dt.month}/{dt.day} {dt.hour:02d}:{dt.minute:02d}"

    def apps(self, user: str) -> list:
        result = []
        for app_id in self._order:
            a = self._apps.get(app_id)
            if a is None or a["user"] != user:
                continue
            result.append({
                "id": a["id"],
                "company": a["company"],
                "deadline": self._fmt_deadline(a["deadline_dt"]),
                "status": a["status"],
            })
        return result

    def due_soon(self, user: str) -> list:
        threshold = self._now + timedelta(days=3)
        candidates = []
        for app_id in self._order:
            a = self._apps.get(app_id)
            if a is None or a["user"] != user:
                continue
            if a["status"] != "draft":
                continue
            if a["deadline_dt"] <= threshold:
                candidates.append(a)
        candidates.sort(key=lambda a: a["deadline_dt"])
        return [
            {
                "id": a["id"],
                "company": a["company"],
                "deadline": self._fmt_deadline(a["deadline_dt"]),
                "status": a["status"],
            }
            for a in candidates
        ]

    def tick(self) -> list:
        now = self._now
        if now.hour != 21 or now.minute != 0:
            return []
        key = (now.year, now.month, now.day, now.hour, now.minute)
        with self._global_lock:
            if self._notified_at == key:
                return []
            self._notified_at = key

        # gather all users
        users = set()
        for app_id in self._order:
            a = self._apps.get(app_id)
            if a is not None:
                users.add(a["user"])

        notified = []
        threshold = now + timedelta(days=3)
        for app_id in self._order:
            a = self._apps.get(app_id)
            if a is None:
                continue
            if a["status"] != "draft":
                continue
            if a["deadline_dt"] <= threshold:
                notified.append((a["user"], a["company"]))
        return notified

    def move(self, user: str, app_id: str, to: str) -> None:
        if to not in _STATUS_ORDER:
            raise ValueError("invalid target status")

        lock = self._app_locks.get(app_id)
        if lock is None:
            raise ValueError("no such application")

        with lock:
            a = self._apps.get(app_id)
            if a is None or a["user"] != user:
                raise ValueError("no such application")

            current = a["status"]

            if current == "failed" and to == "passed":
                # failed の後に passed が来てもエラーにせず failed のまま維持
                return

            if current == "passed" and to == "failed":
                a["status"] = "failed"
                return

            if to == current:
                return

            if to in _ALLOWED_MOVES.get(current, set()):
                a["status"] = to
                return

            raise ValueError(f"cannot move from {current} to {to}")

    def color(self, status: str) -> str:
        return _COLORS.get(status, "gray")

    def extract_deadline(self, mail: str) -> str:
        # 「月/日 時:分」形式の候補を探す。曖昧・複数候補・年推測が必要な場合は None。
        pattern = re.compile(
            r"(\d{1,2})/(\d{1,2})\s*(?:\([月火水木金土日]\))?\s*(\d{1,2}):(\d{2})"
        )
        matches = pattern.findall(mail)
        if len(matches) != 1:
            return None

        month, day, hour, minute = matches[0]
        month = int(month)
        day = int(day)
        hour = int(hour)
        minute = int(minute)

        if not (1 <= month <= 12 and 1 <= day <= 31 and 0 <= hour <= 23 and 0 <= minute <= 59):
            return None

        return f"{month}/{day} {hour:02d}:{minute:02d}"
