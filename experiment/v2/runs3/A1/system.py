from datetime import datetime, timedelta
import re
import threading

class System:
    def __init__(self, now: datetime):
        self.now = now
        self.applications = {}  # user -> {app_id -> {company, deadline, status}}
        self.app_order = {}  # user -> [app_ids in order added]
        self.next_id_counter = 0
        self.lock = threading.Lock()

    def set_now(self, now: datetime) -> None:
        self.now = now

    def add(self, user: str, company: str, deadline: str) -> str:
        with self.lock:
            if user not in self.applications:
                self.applications[user] = {}
                self.app_order[user] = []

            app_id = f"app_{self.next_id_counter}"
            self.next_id_counter += 1

            self.applications[user][app_id] = {
                "company": company,
                "deadline": deadline,
                "status": "draft"
            }
            self.app_order[user].append(app_id)
            return app_id

    def apps(self, user: str) -> list[dict]:
        with self.lock:
            if user not in self.applications:
                return []

            result = []
            for app_id in self.app_order[user]:
                app = self.applications[user][app_id]
                result.append({
                    "id": app_id,
                    "company": app["company"],
                    "deadline": app["deadline"],
                    "status": app["status"]
                })
            return result

    def due_soon(self, user: str) -> list[dict]:
        with self.lock:
            if user not in self.applications:
                return []

            due_apps = []

            for app_id in self.app_order[user]:
                app = self.applications[user][app_id]

                if app["status"] != "draft":
                    continue

                deadline_dt = self._parse_deadline(app["deadline"])
                if deadline_dt is None:
                    continue

                # Check if deadline is within 3 days from now
                # "3日以内" means from now until 3 days later at 23:59
                three_days_later = self.now.replace(hour=23, minute=59, second=59)
                three_days_later = three_days_later + timedelta(days=3)

                if self.now < deadline_dt <= three_days_later:
                    due_apps.append({
                        "id": app_id,
                        "company": app["company"],
                        "deadline": app["deadline"],
                        "status": app["status"],
                        "deadline_dt": deadline_dt
                    })

            # Sort by deadline
            due_apps.sort(key=lambda x: x["deadline_dt"])

            # Remove temporary deadline_dt field
            for app in due_apps:
                del app["deadline_dt"]

            return due_apps

    def _parse_deadline(self, deadline: str) -> datetime | None:
        # deadline format: "9/24 23:59"
        parts = deadline.split()
        if len(parts) != 2:
            return None

        date_part = parts[0]
        time_part = parts[1]

        date_components = date_part.split('/')
        time_components = time_part.split(':')

        if len(date_components) != 2 or len(time_components) != 2:
            return None

        try:
            month = int(date_components[0])
            day = int(date_components[1])
            hour = int(time_components[0])
            minute = int(time_components[1])

            year = self.now.year
            return datetime(year, month, day, hour, minute)
        except (ValueError, TypeError):
            return None

    def tick(self) -> list[tuple[str, str]]:
        if self.now.hour != 21 or self.now.minute != 0:
            return []

        notifications = []

        with self.lock:
            for user in self.applications:
                due_apps = self.due_soon(user)
                for app in due_apps:
                    notifications.append((user, app["company"]))

        return notifications

    def move(self, user: str, app_id: str, to: str) -> None:
        with self.lock:
            if user not in self.applications or app_id not in self.applications[user]:
                raise ValueError("Application not found")

            app = self.applications[user][app_id]
            current_status = app["status"]

            # Validate state transitions
            if current_status == "draft":
                if to != "submitted":
                    raise ValueError(f"Cannot move from draft to {to}")
            elif current_status == "submitted":
                if to not in ("passed", "failed"):
                    raise ValueError(f"Cannot move from submitted to {to}")
            elif current_status == "passed":
                # Passed can be overwritten by failed
                if to != "failed":
                    raise ValueError(f"Cannot move from passed to {to}")
            elif current_status == "failed":
                # Failed is terminal, ignore passed
                if to == "passed":
                    return
                else:
                    raise ValueError(f"Cannot move from failed to {to}")

            app["status"] = to

    def color(self, status: str) -> str:
        colors = {
            "draft": "orange",
            "submitted": "blue",
            "passed": "green",
            "failed": "gray"
        }
        return colors.get(status, "gray")

    def extract_deadline(self, mail: str) -> str | None:
        # Normalize full-width digits and symbols to half-width
        normalized = self._normalize_full_width(mail)

        # Pattern: month/day hour:minute
        # Looking for patterns like "9/24 23:59" or "10/15 12:00"
        pattern = r'(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})'

        match = re.search(pattern, normalized)
        if match:
            month = match.group(1)
            day = match.group(2)
            hour = match.group(3)
            minute = match.group(4)
            return f"{month}/{day} {hour}:{minute}"

        return None

    def _normalize_full_width(self, text: str) -> str:
        # Map full-width characters to half-width
        full_to_half = {
            '0': '0', '1': '1', '2': '2', '3': '3', '4': '4',
            '5': '5', '6': '6', '7': '7', '8': '8', '9': '9',
            '／': '/', '：': ':', '（': '(', '）': ')'
        }

        result = []
        for char in text:
            if char in full_to_half:
                result.append(full_to_half[char])
            else:
                result.append(char)

        return ''.join(result)
