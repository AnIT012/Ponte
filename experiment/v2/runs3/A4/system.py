from datetime import datetime, timedelta
import re
import threading

class System:
    def __init__(self, now: datetime):
        self.now = now
        self.apps_by_user = {}  # user -> list of apps
        self.app_data = {}  # app_id -> {user, company, deadline, status}
        self.counter = 0
        self.thread_lock = threading.Lock()

    def set_now(self, now: datetime) -> None:
        self.now = now

    def add(self, user: str, company: str, deadline: str) -> str:
        with self.thread_lock:
            app_id = f"app{self.counter}"
            self.counter += 1

            if user not in self.apps_by_user:
                self.apps_by_user[user] = []

            self.app_data[app_id] = {
                "user": user,
                "company": company,
                "deadline": deadline,
                "status": "draft"
            }
            self.apps_by_user[user].append(app_id)

            return app_id

    def apps(self, user: str) -> list[dict]:
        with self.thread_lock:
            if user not in self.apps_by_user:
                return []

            result = []
            for app_id in self.apps_by_user[user]:
                app_info = self.app_data[app_id]
                result.append({
                    "id": app_id,
                    "company": app_info["company"],
                    "deadline": app_info["deadline"],
                    "status": app_info["status"]
                })
            return result

    def due_soon(self, user: str) -> list[dict]:
        with self.thread_lock:
            if user not in self.apps_by_user:
                return []

            due_list = []

            for app_id in self.apps_by_user[user]:
                app_info = self.app_data[app_id]

                if app_info["status"] != "draft":
                    continue

                deadline_dt = self._parse_time(app_info["deadline"])
                if deadline_dt is None:
                    continue

                # Within 3 days
                limit = self.now + timedelta(days=3)
                limit = limit.replace(hour=23, minute=59, second=59)

                if self.now < deadline_dt <= limit:
                    due_list.append({
                        "id": app_id,
                        "company": app_info["company"],
                        "deadline": app_info["deadline"],
                        "status": app_info["status"],
                        "ts": deadline_dt
                    })

            due_list.sort(key=lambda x: x["ts"])

            for item in due_list:
                del item["ts"]

            return due_list

    def _parse_time(self, deadline: str) -> datetime | None:
        try:
            parts = deadline.split()
            if len(parts) != 2:
                return None

            date_part = parts[0]
            time_part = parts[1]

            month, day = map(int, date_part.split('/'))
            hour, minute = map(int, time_part.split(':'))

            year = self.now.year
            return datetime(year, month, day, hour, minute)
        except (ValueError, IndexError):
            return None

    def tick(self) -> list[tuple[str, str]]:
        if self.now.hour != 21 or self.now.minute != 0:
            return []

        notifications = []

        with self.thread_lock:
            for user in self.apps_by_user:
                soon_apps = self.due_soon(user)
                for app in soon_apps:
                    notifications.append((user, app["company"]))

        return notifications

    def move(self, user: str, app_id: str, to: str) -> None:
        with self.thread_lock:
            if app_id not in self.app_data:
                raise ValueError("Application not found")

            app_info = self.app_data[app_id]

            if app_info["user"] != user:
                raise ValueError("Access denied")

            current = app_info["status"]

            # State validation
            if current == "draft":
                if to != "submitted":
                    raise ValueError(f"Cannot transition from draft to {to}")
            elif current == "submitted":
                if to not in ("passed", "failed"):
                    raise ValueError(f"Cannot transition from submitted to {to}")
            elif current == "passed":
                if to == "failed":
                    app_info["status"] = to
                    return
                else:
                    raise ValueError(f"Cannot transition from passed to {to}")
            elif current == "failed":
                # Failed is final; passed is ignored
                if to == "passed":
                    return
                raise ValueError(f"Cannot transition from failed")
                return

            app_info["status"] = to

    def color(self, status: str) -> str:
        colors = {
            "draft": "orange",
            "submitted": "blue",
            "passed": "green",
            "failed": "gray"
        }
        return colors.get(status, "gray")

    def extract_deadline(self, mail: str) -> str | None:
        mail_norm = self._to_half_width(mail)

        # Find deadline pattern
        pattern = r'(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})'
        m = re.search(pattern, mail_norm)

        if m:
            return f"{m.group(1)}/{m.group(2)} {m.group(3)}:{m.group(4)}"

        return None

    def _to_half_width(self, text: str) -> str:
        # Convert full-width to half-width
        mapping = {
            '０': '0', '１': '1', '２': '2', '３': '3', '４': '4',
            '５': '5', '６': '6', '７': '7', '８': '8', '９': '9',
            '／': '/', '：': ':', '（': '(', '）': ')'
        }

        result = []
        for char in text:
            if char in mapping:
                result.append(mapping[char])
            else:
                result.append(char)

        return ''.join(result)
