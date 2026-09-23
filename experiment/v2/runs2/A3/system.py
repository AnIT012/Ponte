# Q: 「今の時刻が21:00なら」の判定は、set_now/コンストラクタで与えられた datetime の
#     時・分が (21, 0) と一致する場合とした（秒・マイクロ秒は無視）。
# Q: 1日に複数回 tick() が21:00ちょうどのまま呼ばれた場合の重複通知防止は要件に無いため、
#     「今がちょうど21:00かどうか」だけで判定し、同じ21:00でtickを2回呼べば2回通知される仕様とした。
# Q: deadline の年は「今の年」固定。年をまたぐ締切（例:12月末に1月の締切を足す）の扱いは指定が無いため、
#     常に System が保持する now の年を使うこととした。
# Q: extract_deadline で複数の日時候補が見つかった場合は自信が無いとみなし None を返す。
# Q: extract_deadline は年を含む文字列があっても年は無視し、月/日 時:分のみを見る。
# Q: move() で同じ状態への遷移（例: submitted -> submitted）は「順番に反する」として ValueError とした。
# Q: due_soon の「3日以内」は日付基準。今日を含めて3日後の日付の23:59までとした
#     （例のとおり 9/21 21:00 時点で 9/24 23:59 の締切は対象）。

import re
import threading
import uuid
from datetime import datetime, timedelta

_STATUS_ORDER = ["draft", "submitted", "passed", "failed"]

_NEXT = {
    "draft": {"submitted"},
    "submitted": {"passed", "failed"},
    "passed": {"failed"},   # passed -> failed は上書き許可（エラーにしない）
    "failed": set(),        # failed -> passed はエラーにはせず「無視」して failed のまま維持
}

_COLORS = {
    "draft": "orange",
    "submitted": "blue",
    "passed": "green",
    "failed": "gray",
}

_ZEN2HAN = str.maketrans({
    "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
    "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
    "／": "/", "：": ":", "（": "(", "）": ")",
})

_DEADLINE_RE = re.compile(
    r"(\d{1,2})\s*/\s*(\d{1,2})\s*(?:\([^)]*\))?\s*(\d{1,2})\s*:\s*(\d{2})"
)


class _App:
    __slots__ = ("id", "user", "company", "deadline", "status", "lock")

    def __init__(self, id_, user, company, deadline):
        self.id = id_
        self.user = user
        self.company = company
        self.deadline = deadline
        self.status = "draft"
        self.lock = threading.Lock()


class System:
    def __init__(self, now: datetime):
        self._now = now
        self._apps: dict[str, _App] = {}
        self._order: list[str] = []
        self._global_lock = threading.Lock()

    def set_now(self, now: datetime) -> None:
        self._now = now

    def add(self, user: str, company: str, deadline: str) -> str:
        dt = self._parse_deadline(deadline)
        app_id = uuid.uuid4().hex
        app = _App(app_id, user, company, dt)
        with self._global_lock:
            self._apps[app_id] = app
            self._order.append(app_id)
        return app_id

    def apps(self, user: str) -> list[dict]:
        result = []
        for app_id in self._order:
            app = self._apps.get(app_id)
            if app is not None and app.user == user:
                result.append(self._to_dict(app))
        return result

    def due_soon(self, user: str) -> list[dict]:
        now = self._now
        limit = datetime(now.year, now.month, now.day, 23, 59) + timedelta(days=3)
        items = []
        for app_id in self._order:
            app = self._apps.get(app_id)
            if app is None or app.user != user:
                continue
            if app.status != "draft":
                continue
            dt = self._parse_deadline(app.deadline)
            if dt < now:
                continue
            if dt > limit:
                continue
            items.append(app)
        items.sort(key=lambda a: self._parse_deadline(a.deadline))
        return [self._to_dict(a) for a in items]

    def tick(self) -> list[tuple[str, str]]:
        now = self._now
        if (now.hour, now.minute) != (21, 0):
            return []
        notified = []
        with self._global_lock:
            user_apps = {}
            for app_id in self._order:
                app = self._apps.get(app_id)
                if app is None:
                    continue
                user_apps.setdefault(app.user, []).append(app)

        for user, app_list in user_apps.items():
            due = self.due_soon(user)
            due_ids = [d["id"] for d in due]
            id_to_app = {a.id: a for a in app_list}
            for aid in due_ids:
                app = id_to_app.get(aid)
                if app is not None:
                    notified.append((app.user, app.company))
        return notified

    def move(self, user: str, app_id: str, to: str) -> None:
        app = self._apps.get(app_id)
        if app is None or app.user != user:
            raise ValueError("no such application for this user")
        if to not in _STATUS_ORDER:
            raise ValueError("invalid status")

        with app.lock:
            current = app.status
            if to == current:
                if current in ("passed", "failed") and to == current:
                    raise ValueError(f"cannot move from {current} to {to}")
                raise ValueError(f"cannot move from {current} to {to}")

            if current == "passed" and to == "failed":
                app.status = "failed"
                return
            if current == "failed" and to == "passed":
                # 不合格優先。エラーにはしないが、状態は failed のまま。
                return

            if to in _NEXT.get(current, set()):
                app.status = to
                return

            raise ValueError(f"cannot move from {current} to {to}")

    def color(self, status: str) -> str:
        return _COLORS.get(status, "gray")

    def extract_deadline(self, mail: str) -> str | None:
        text = mail.translate(_ZEN2HAN)
        matches = list(_DEADLINE_RE.finditer(text))
        if len(matches) != 1:
            return None
        m = matches[0]
        month, day, hour, minute = (int(g) for g in m.groups())
        if not (1 <= month <= 12 and 1 <= day <= 31):
            return None
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        return f"{month}/{day} {hour:02d}:{minute:02d}"

    def _parse_deadline(self, deadline: str) -> datetime:
        m = re.match(r"(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})", deadline.strip())
        if not m:
            raise ValueError(f"invalid deadline format: {deadline}")
        month, day, hour, minute = (int(g) for g in m.groups())
        return datetime(self._now.year, month, day, hour, minute)

    def _to_dict(self, app: _App) -> dict:
        return {
            "id": app.id,
            "company": app.company,
            "deadline": app.deadline,
            "status": app.status,
        }
