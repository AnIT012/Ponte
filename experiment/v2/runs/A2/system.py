# Q: 「締切が近い」の3日以内は、切り捨てで72時間以内(今から3日後の同時刻まで)と解釈した。
# Q: tick() は「今の時刻がちょうど21:00(時=21,分=0)」の場合に動くと解釈し、同じ日の21:00に複数回呼ばれても
#     二重通知しないよう、ユーザーごと・日付ごとに通知済みを記録することにした。
# Q: 通知の送信先・内容は「(持ち主, 会社名)」のタプルをtick()の戻り値として返すことのみとし、実際のメール送信等は行わない。
# Q: extract_deadline は「月/日 時:分」形式のみ対応。複数候補がある場合や範囲・「または」がある場合は None を返す。
#    西暦の指定がある場合(例: 2024/10/15)は年月日を無視して月/日のみを使う、とはせず、
#    このフォーマットは年を含まない前提のため、年が明示されている表記は対象外(None)とした。
# Q: move() で from==to など無意味な遷移(例: draft->draft)はエラーとした。
#    ただし passed->passed, failed->failed は「同じ状態への再通知」として許容(no-op)。
# Q: due_soon の対象は status=="draft" のみ(要件通り)。締切が過去(既に切れている)ものは対象外とした。
# Q: id は "app-<連番>" という形式の文字列とした。
# Q: set_now は tick() の通知済み記録をリセットしない(時刻を戻してテストする場合は別日として扱われる)。

import re
import threading
from datetime import datetime, timedelta

_STATUS_ORDER = {
    "draft": 0,
    "submitted": 1,
    "passed": 2,
    "failed": 2,
}

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

_MONTH_DAY_TIME_RE = re.compile(
    r"(?<!\d)(\d{1,2})/(\d{1,2})(?:\([^)]*\))?\s*(\d{1,2}):(\d{2})(?!\d)"
)


class _Application:
    __slots__ = ("id", "user", "company", "deadline", "status", "lock")

    def __init__(self, app_id, user, company, deadline):
        self.id = app_id
        self.user = user
        self.company = company
        self.deadline = deadline
        self.status = "draft"
        self.lock = threading.Lock()


class System:
    def __init__(self, now: datetime):
        self._now = now
        self._apps: dict[str, _Application] = {}
        self._order: list[str] = []
        self._next_id = 1
        self._global_lock = threading.Lock()
        self._notified_dates: set[tuple[str, str]] = set()  # (user_or_all_marker, date_str)
        self._notified_days: set[str] = set()

    def set_now(self, now: datetime) -> None:
        self._now = now

    def add(self, user: str, company: str, deadline: str) -> str:
        with self._global_lock:
            app_id = f"app-{self._next_id}"
            self._next_id += 1
            year = self._now.year
            deadline_dt = self._parse_deadline(deadline, year)
            app = _Application(app_id, user, company, deadline_dt)
            self._apps[app_id] = app
            self._order.append(app_id)
            return app_id

    def _parse_deadline(self, deadline: str, year: int) -> datetime:
        m = re.match(r"^\s*(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})\s*$", deadline)
        if not m:
            raise ValueError(f"invalid deadline format: {deadline}")
        month, day, hour, minute = (int(x) for x in m.groups())
        return datetime(year, month, day, hour, minute)

    def apps(self, user: str) -> list[dict]:
        result = []
        for app_id in self._order:
            app = self._apps[app_id]
            if app.user != user:
                continue
            result.append(self._to_dict(app))
        return result

    def _to_dict(self, app: _Application) -> dict:
        return {
            "id": app.id,
            "company": app.company,
            "deadline": self._format_deadline(app.deadline),
            "status": app.status,
        }

    def _format_deadline(self, dt: datetime) -> str:
        return f"{dt.month}/{dt.day} {dt.hour:02d}:{dt.minute:02d}"

    def due_soon(self, user: str) -> list[dict]:
        now = self._now
        threshold = now + timedelta(days=3)
        result = []
        for app_id in self._order:
            app = self._apps[app_id]
            if app.user != user:
                continue
            if app.status != "draft":
                continue
            if now <= app.deadline <= threshold:
                result.append(app)
        result.sort(key=lambda a: a.deadline)
        return [self._to_dict(a) for a in result]

    def tick(self) -> list[tuple[str, str]]:
        now = self._now
        if now.hour != 21 or now.minute != 0:
            return []

        date_key = now.strftime("%Y-%m-%d")
        with self._global_lock:
            if date_key in self._notified_days:
                return []
            self._notified_days.add(date_key)

        threshold = now + timedelta(days=3)
        notified = []
        for app_id in self._order:
            app = self._apps[app_id]
            with app.lock:
                if app.status != "draft":
                    continue
                if now <= app.deadline <= threshold:
                    notified.append((app.user, app.company))
        return notified

    def move(self, user: str, app_id: str, to: str) -> None:
        if to not in _STATUS_ORDER:
            raise ValueError(f"invalid status: {to}")

        app = self._apps.get(app_id)
        if app is None or app.user != user:
            raise ValueError("no such application for this user")

        with app.lock:
            current = app.status
            if current == "failed" and to == "passed":
                # passed after failed: stays failed, not an error
                return
            if current == "passed" and to == "failed":
                app.status = "failed"
                return
            if to == current:
                if current in ("passed", "failed"):
                    return
                raise ValueError(f"invalid transition: {current} -> {to}")
            allowed = _ALLOWED_TRANSITIONS.get(current, set())
            if to not in allowed:
                raise ValueError(f"invalid transition: {current} -> {to}")
            app.status = to

    def color(self, status: str) -> str:
        return _COLORS.get(status, "gray")

    def extract_deadline(self, mail: str) -> str | None:
        matches = _MONTH_DAY_TIME_RE.findall(mail)
        if len(matches) != 1:
            return None
        month, day, hour, minute = matches[0]
        month_i, day_i, hour_i, minute_i = int(month), int(day), int(hour), int(minute)
        if not (1 <= month_i <= 12):
            return None
        if not (1 <= day_i <= 31):
            return None
        if not (0 <= hour_i <= 23):
            return None
        if not (0 <= minute_i <= 59):
            return None
        return f"{month_i}/{day_i} {hour_i:02d}:{minute_i:02d}"
