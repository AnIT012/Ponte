# Q: 通知の実際の送信方法（メール送信など）は指定されていないため、送信は行わず対象を返すだけにしました。
# Q: tick() は「21:00」を時=21, 分=0 の瞬間とみなし、その分ちょうどに一度だけ呼ばれる想定としました（同じ分に複数回呼ばれた場合の重複防止までは仕様にないため実装していません）。
# Q: tick() が返す通知の順番は、全ユーザーを通して応募が追加された順（add した順）としました。
# Q: extract_deadline は「月/日 時:分」の形式にマッチする箇所がちょうど1つだけ見つかった場合のみ値を返し、0個または2個以上見つかった場合は None（自信がない）としました。
# Q: 年をまたぐ締切（例: 12月に登録した後、翌年1月が締切）の扱いは仕様に無いため、単純に「今の年」を使うこととしました。
# Q: move() で to に不正な文字列（draft/submitted/passed/failed 以外）が渡された場合も ValueError としました。
# Q: 応募が見つからない id が move() に渡された場合も ValueError としました（他人の応募と同様に扱う）。

import re
import threading
import uuid
from datetime import datetime, timedelta

_STATUS_ORDER = {"draft": 0, "submitted": 1, "passed": 2, "failed": 2}

_ALLOWED_TRANSITIONS = {
    "draft": {"submitted"},
    "submitted": {"passed", "failed"},
    "passed": {"failed"},   # failed が来たら上書き
    "failed": {"passed"},   # passed が来ても無視してエラーにはしない
}

_COLORS = {
    "draft": "orange",
    "submitted": "blue",
    "passed": "green",
    "failed": "gray",
}

_ZENKAKU_TABLE = str.maketrans({
    "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
    "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
    "／": "/", "：": ":", "（": "(", "）": ")",
    "　": " ",
})

_DEADLINE_RE = re.compile(
    r'(\d{1,2})/(\d{1,2})(?:\([月火水木金土日]\))?\s*(\d{1,2}):(\d{2})'
)


class System:
    def __init__(self, now: datetime):
        self._now = now
        self._apps = []  # list of dict, insertion order preserved
        self._apps_by_id = {}
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
        dt = self._parse_deadline_str(deadline)
        app_id = uuid.uuid4().hex
        app = {
            "id": app_id,
            "user": user,
            "company": company,
            "deadline": deadline,
            "deadline_dt": dt,
            "status": "draft",
        }
        with self._global_lock:
            self._apps.append(app)
            self._apps_by_id[app_id] = app
            self._app_locks[app_id] = threading.Lock()
        return app_id

    def _parse_deadline_str(self, deadline: str) -> datetime:
        m = re.match(r'(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})', deadline)
        month, day, hour, minute = (int(x) for x in m.groups())
        return datetime(self._now.year, month, day, hour, minute)

    def apps(self, user: str) -> list:
        with self._global_lock:
            result = []
            for app in self._apps:
                if app["user"] == user:
                    result.append({
                        "id": app["id"],
                        "company": app["company"],
                        "deadline": app["deadline"],
                        "status": app["status"],
                    })
            return result

    def due_soon(self, user: str) -> list:
        now = self._now
        cutoff_date = (now + timedelta(days=3)).date()
        cutoff = datetime(cutoff_date.year, cutoff_date.month, cutoff_date.day, 23, 59)
        with self._global_lock:
            candidates = []
            for app in self._apps:
                if app["user"] != user:
                    continue
                if app["status"] != "draft":
                    continue
                dt = app["deadline_dt"]
                if dt < now:
                    continue
                if dt > cutoff:
                    continue
                candidates.append(app)
            candidates.sort(key=lambda a: a["deadline_dt"])
            return [
                {
                    "id": a["id"],
                    "company": a["company"],
                    "deadline": a["deadline"],
                    "status": a["status"],
                }
                for a in candidates
            ]

    def tick(self) -> list:
        now = self._now
        if now.hour != 21 or now.minute != 0:
            return []

        cutoff_date = (now + timedelta(days=3)).date()
        cutoff = datetime(cutoff_date.year, cutoff_date.month, cutoff_date.day, 23, 59)

        notified = []
        with self._global_lock:
            for app in self._apps:
                if app["status"] != "draft":
                    continue
                dt = app["deadline_dt"]
                if dt < now:
                    continue
                if dt > cutoff:
                    continue
                notified.append((app["user"], app["company"]))
        return notified

    def move(self, user: str, app_id: str, to: str) -> None:
        if to not in _STATUS_ORDER:
            raise ValueError(f"invalid target status: {to}")

        lock = self._get_app_lock(app_id)
        with lock:
            with self._global_lock:
                app = self._apps_by_id.get(app_id)
                if app is None or app["user"] != user:
                    raise ValueError("application not found or not owned by user")
                current = app["status"]

            if current == to:
                return

            allowed = _ALLOWED_TRANSITIONS.get(current, set())
            if to not in allowed:
                raise ValueError(f"cannot move from {current} to {to}")

            with self._global_lock:
                app["status"] = to

    def color(self, status: str) -> str:
        return _COLORS.get(status, "gray")

    def extract_deadline(self, mail: str) -> str:
        text = mail.translate(_ZENKAKU_TABLE)
        matches = list(_DEADLINE_RE.finditer(text))
        if len(matches) != 1:
            return None
        month, day, hour, minute = matches[0].groups()
        return f"{int(month)}/{int(day)} {int(hour)}:{minute}"
