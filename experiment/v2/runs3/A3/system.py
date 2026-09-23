from datetime import datetime, timedelta
import re
import threading

class System:
    def __init__(self, now: datetime):
        self.current_time = now
        self.users = {}  # user -> {app_id -> app_info}
        self.user_order = {}  # user -> [app_ids]
        self.id_gen = 0
        self.lock = threading.Lock()

    def set_now(self, now: datetime) -> None:
        self.current_time = now

    def add(self, user: str, company: str, deadline: str) -> str:
        with self.lock:
            if user not in self.users:
                self.users[user] = {}
                self.user_order[user] = []

            app_id = str(self.id_gen)
            self.id_gen += 1

            self.users[user][app_id] = {
                "company": company,
                "deadline": deadline,
                "status": "draft"
            }
            self.user_order[user].append(app_id)
            return app_id

    def apps(self, user: str) -> list[dict]:
        with self.lock:
            if user not in self.users:
                return []

            apps_list = []
            for app_id in self.user_order[user]:
                app_info = self.users[user][app_id]
                apps_list.append({
                    "id": app_id,
                    "company": app_info["company"],
                    "deadline": app_info["deadline"],
                    "status": app_info["status"]
                })
            return apps_list

    def due_soon(self, user: str) -> list[dict]:
        with self.lock:
            if user not in self.users:
                return []

            due_apps = []

            for app_id in self.user_order[user]:
                app_info = self.users[user][app_id]

                if app_info["status"] != "draft":
                    continue

                deadline_dt = self._parse_deadline(app_info["deadline"])
                if deadline_dt is None:
                    continue

                # Check if within 3 days: now < deadline <= (now + 3 days at 23:59)
                cutoff = self.current_time + timedelta(days=3)
                cutoff = cutoff.replace(hour=23, minute=59, second=59)

                if self.current_time < deadline_dt <= cutoff:
                    due_apps.append({
                        "id": app_id,
                        "company": app_info["company"],
                        "deadline": app_info["deadline"],
                        "status": app_info["status"],
                        "_deadline_dt": deadline_dt
                    })

            # Sort by deadline
            due_apps.sort(key=lambda x: x["_deadline_dt"])

            # Remove temp field
            for app in due_apps:
                del app["_deadline_dt"]

            return due_apps

    def _parse_deadline(self, deadline: str) -> datetime | None:
        try:
            parts = deadline.split()
            if len(parts) != 2:
                return None

            date_str, time_str = parts
            month, day = map(int, date_str.split('/'))
            hour, minute = map(int, time_str.split(':'))

            year = self.current_time.year
            return datetime(year, month, day, hour, minute)
        except (ValueError, AttributeError, IndexError):
            return None

    def tick(self) -> list[tuple[str, str]]:
        if self.current_time.hour != 21 or self.current_time.minute != 0:
            return []

        notifications = []

        with self.lock:
            for user in self.users:
                due_apps = self.due_soon(user)
                for app in due_apps:
                    notifications.append((user, app["company"]))

        return notifications

    def move(self, user: str, app_id: str, to: str) -> None:
        with self.lock:
            if user not in self.users:
                raise ValueError("User not found")
            if app_id not in self.users[user]:
                raise ValueError("Application not found")

            app = self.users[user][app_id]
            current = app["status"]

            # Validate transitions
            if current == "draft":
                if to != "submitted":
                    raise ValueError(f"Cannot move from draft to {to}")
            elif current == "submitted":
                if to not in ("passed", "failed"):
                    raise ValueError(f"Cannot move from submitted to {to}")
            elif current == "passed":
                if to == "failed":
                    app["status"] = to
                else:
                    raise ValueError(f"Cannot move from passed to {to}")
            elif current == "failed":
                # Failed is terminal; failed takes priority
                if to == "passed":
                    # Ignore - don't update
                    return
                else:
                    raise ValueError(f"Cannot move from failed to {to}")
                return

            app["status"] = to

    def color(self, status: str) -> str:
        status_colors = {
            "draft": "orange",
            "submitted": "blue",
            "passed": "green",
            "failed": "gray"
        }
        return status_colors.get(status, "gray")

    def extract_deadline(self, mail: str) -> str | None:
        # Normalize full-width characters
        normalized = self._normalize_fw(mail)

        # Pattern: m/d h:mm or mm/dd hh:mm
        pattern = r'(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})'

        match = re.search(pattern, normalized)
        if match:
            m, d, h, min = match.groups()
            return f"{m}/{d} {h}:{min}"

        return None

    def _normalize_fw(self, text: str) -> str:
        # Map full-width to half-width
        fw_chars = {
            '０': '0', '１': '1', '２': '2', '３': '3', '４': '4',
            '５': '5', '６': '6', '７': '7', '８': '8', '９': '9',
            '／': '/', '：': ':', '（': '(', '）': ')'
        }

        chars = []
        for c in text:
            chars.append(fw_chars.get(c, c))

        return ''.join(chars)
