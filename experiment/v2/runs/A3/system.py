# Q: 通知の送り先/送信方法は指定がないため、(持ち主, 会社名) のリストを返すのみとし、実際の送信(メール等)は行わない。
# Q: tick() は「ちょうど21:00」の判定を、秒・マイクロ秒を無視し時:分が21:00かどうかで行うと仮定。
# Q: 1日に複数回 21:00 ちょうどで tick() が呼ばれても、毎回同じ「締切が近い応募」があれば通知する（重複抑制の指定がないため）。
# Q: due_soon の「3日以内」は今から72時間以内ではなく、日付ベース(今日を含め3日先まで)ではなく、単純に (deadline - now) が 0 以上 3日以内(<=3日)と解釈。
# Q: 締切を過ぎた draft も due_soon の対象に含めるかは不明。ここでは deadline >= now のもののみ対象とする（過ぎたものは対象外）。
# Q: extract_deadline は月/日と時:分の組を1つだけ見つけた場合のみ返し、複数候補がある場合や範囲・選択肢がある場合は None を返す。
# Q: user の存在確認や company の重複チェックについては指定がないため行わない。
# Q: move() で to が不正な文字列(状態名でない)の場合も ValueError とする。
# Q: move() で同じ状態への遷移(例: submitted -> submitted)は許可しないものとしエラーとする（passed/failed 特殊ケースを除く）。

import re
import threading
from datetime import datetime, timedelta

_STATUSES = ("draft", "submitted", "passed", "failed")

_ALLOWED_TRANSITIONS = {
    "draft": {"submitted"},
    "submitted": {"passed", "failed"},
    "passed": {"failed"},   # failed が優先で上書き可
    "failed": {"passed"},   # passed が来ても failed のまま（エラーにしない）
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
        self._apps = {}  # id -> dict(user, company, deadline: datetime, status)
        self._order = []  # list of ids in add order (global)
        self._next_id = 1
        self._lock = threading.Lock()
        self._app_locks = {}  # id -> threading.Lock

    def set_now(self, now: datetime) -> None:
        self._now = now

    def _get_app_lock(self, app_id: str) -> threading.Lock:
        with self._lock:
            lk = self._app_locks.get(app_id)
            if lk is None:
                lk = threading.Lock()
                self._app_locks[app_id] = lk
            return lk

    def add(self, user: str, company: str, deadline: str) -> str:
        dt = self._parse_deadline(deadline)
        with self._lock:
            app_id = str(self._next_id)
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

    def _parse_deadline(self, deadline: str) -> datetime:
        m = re.match(r"^(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})$", deadline.strip())
        if not m:
            raise ValueError(f"invalid deadline format: {deadline}")
        month, day, hour, minute = (int(x) for x in m.groups())
        year = self._now.year
        return datetime(year, month, day, hour, minute)

    def apps(self, user: str) -> list:
        with self._lock:
            result = []
            for app_id in self._order:
                a = self._apps[app_id]
                if a["user"] == user:
                    result.append(self._to_public(a))
            return result

    def _to_public(self, a: dict) -> dict:
        return {
            "id": a["id"],
            "company": a["company"],
            "deadline": self._format_deadline(a["deadline"]),
            "status": a["status"],
        }

    def _format_deadline(self, dt: datetime) -> str:
        return f"{dt.month}/{dt.day} {dt.hour:02d}:{dt.minute:02d}"

    def due_soon(self, user: str) -> list:
        with self._lock:
            candidates = []
            for app_id in self._order:
                a = self._apps[app_id]
                if a["user"] != user:
                    continue
                if a["status"] != "draft":
                    continue
                delta = a["deadline"] - self._now
                if timedelta(0) <= delta <= timedelta(days=3):
                    candidates.append(a)
            candidates.sort(key=lambda a: a["deadline"])
            return [self._to_public(a) for a in candidates]

    def tick(self) -> list:
        if not (self._now.hour == 21 and self._now.minute == 0):
            return []
        with self._lock:
            candidates = []
            for app_id in self._order:
                a = self._apps[app_id]
                if a["status"] != "draft":
                    continue
                delta = a["deadline"] - self._now
                if timedelta(0) <= delta <= timedelta(days=3):
                    candidates.append(a)
            candidates.sort(key=lambda a: a["deadline"])
            return [(a["user"], a["company"]) for a in candidates]

    def move(self, user: str, app_id: str, to: str) -> None:
        if to not in _STATUSES:
            raise ValueError(f"invalid status: {to}")

        lock = self._get_app_lock(app_id)
        with lock:
            with self._lock:
                a = self._apps.get(app_id)
                if a is None:
                    raise ValueError("app not found")
                if a["user"] != user:
                    raise ValueError("not your application")
                current = a["status"]

            if current == "failed" and to == "passed":
                # failed のままにする（エラーにしない）
                return

            allowed = _ALLOWED_TRANSITIONS.get(current, set())
            if to not in allowed:
                raise ValueError(f"cannot move from {current} to {to}")

            with self._lock:
                a["status"] = to

    def color(self, status: str) -> str:
        return _COLORS.get(status, "gray")

    def extract_deadline(self, mail: str) -> str | None:
        # 月/日 と 時:分 のペアを探す。複数個所見つかった場合は自信がないとみなし None。
        pattern = re.compile(
            r"(\d{1,2})/(\d{1,2})(?:\([^)]*\))?\s*(\d{1,2}):(\d{2})"
        )
        matches = pattern.findall(mail)
        if len(matches) != 1:
            return None
        month, day, hour, minute = matches[0]
        month, day, hour, minute = int(month), int(day), int(hour), int(minute)
        if not (1 <= month <= 12 and 1 <= day <= 31 and 0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        return f"{month}/{day} {hour:02d}:{minute:02d}"
