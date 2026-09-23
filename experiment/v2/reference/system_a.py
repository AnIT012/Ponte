"""(A) の条件で、要件を全部満たす参照実装（人が書いたもの）。採点テストが通せることの確認に使う。AIの出力ではない。"""
import re
import threading
import unicodedata
from datetime import datetime, timedelta

FLOW = {"draft": {"submitted"}, "submitted": {"passed", "failed"}}
COLORS = {"draft": "orange", "submitted": "blue", "passed": "green", "failed": "gray"}


class System:
    def __init__(self, now: datetime):
        self.now = now
        self.apps_ = []
        self.lock = threading.Lock()
        self.n = 0

    def set_now(self, now):
        self.now = now

    def _t(self, s):
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2}) (\d{1,2}):(\d{2})", s)
        return datetime(self.now.year, int(m[1]), int(m[2]), int(m[3]), int(m[4]))

    def add(self, user, company, deadline):
        with self.lock:
            self.n += 1
            a = {"id": f"a{self.n}", "company": company, "deadline": deadline, "status": "draft",
                 "user": user, "prev": None, "lock": threading.Lock()}
            self.apps_.append(a)
            return a["id"]

    def _pub(self, a):
        return {k: a[k] for k in ("id", "company", "deadline", "status")}

    def apps(self, user):
        return [self._pub(a) for a in self.apps_ if a["user"] == user]

    def due_soon(self, user):
        end = (self.now + timedelta(days=3)).replace(hour=23, minute=59, second=59)
        xs = [a for a in self.apps_ if a["user"] == user and a["status"] == "draft" and self.now <= self._t(a["deadline"]) <= end]
        return [self._pub(a) for a in sorted(xs, key=lambda a: self._t(a["deadline"]))]

    def tick(self):
        if (self.now.hour, self.now.minute) != (21, 0):
            return []
        users = list(dict.fromkeys(a["user"] for a in self.apps_))
        return [(u, x["company"]) for u in users for x in self.due_soon(u)]

    def move(self, user, app_id, to):
        a = next((a for a in self.apps_ if a["id"] == app_id), None)
        if a is None or a["user"] != user:
            raise ValueError("他人の応募か、ありません")
        with a["lock"]:
            cur = a["status"]
            if cur == to:
                return
            if to in FLOW.get(cur, ()):
                a["prev"], a["status"] = cur, to
                return
            if a["prev"] == "submitted" and {cur, to} == {"passed", "failed"}:
                a["status"] = "failed"
                return
            raise ValueError(f"{cur} から {to} へは動けません")

    def color(self, status):
        return COLORS.get(status, "gray")

    def extract_deadline(self, mail):
        t = unicodedata.normalize("NFKC", mail)
        hits = re.findall(r"(\d{1,2})/(\d{1,2})(?:\(.\))?\s*(\d{1,2}):(\d{2})", t)
        if len(hits) != 1:
            return None
        mo, d, h, mi = hits[0]
        return f"{int(mo)}/{int(d)} {int(h)}:{mi}"
