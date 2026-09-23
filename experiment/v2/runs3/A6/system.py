# Q: Applications are identified by a simple incrementing integer ID
# Q: Thread safety is implemented per-application using locks, not a global lock
# Q: Deadline string input uses "M/D H:MM" or "MM/DD HH:MM" format; year is assumed current year
# Q: When extracting deadline, full-width digits/symbols are converted to half-width equivalents
# Q: The "3 days within" calculation: if today is 9/21, 3 days within means up to 9/24 23:59

from datetime import datetime, timedelta
import re
import threading
from typing import Optional

class System:
    def __init__(self, now: datetime):
        self.now = now
        self.applications = {}  # user -> {app_id -> app}
        self.next_id = 0
        self.id_lock = threading.Lock()
        self.app_locks = {}  # app_id -> lock

    def set_now(self, now: datetime) -> None:
        self.now = now

    def _get_app_lock(self, app_id: str) -> threading.Lock:
        if app_id not in self.app_locks:
            self.app_locks[app_id] = threading.Lock()
        return self.app_locks[app_id]

    def _parse_deadline(self, deadline_str: str) -> datetime:
        """Parse deadline string like '9/24 23:59' to datetime object."""
        # Format: "M/D H:MM" or "MM/DD HH:MM"
        parts = deadline_str.split()
        date_part = parts[0]  # "9/24"
        time_part = parts[1]  # "23:59"

        month, day = map(int, date_part.split('/'))
        hour, minute = map(int, time_part.split(':'))

        year = self.now.year
        return datetime(year, month, day, hour, minute, 0)

    def _days_between_dates(self, d1: datetime, d2: datetime) -> int:
        """Calculate days between two dates (just the date part, not time)."""
        return (d2.date() - d1.date()).days

    def add(self, user: str, company: str, deadline: str) -> str:
        """Add an application and return its ID."""
        with self.id_lock:
            app_id = str(self.next_id)
            self.next_id += 1

        deadline_dt = self._parse_deadline(deadline)

        if user not in self.applications:
            self.applications[user] = {}

        app = {
            "id": app_id,
            "company": company,
            "deadline": deadline_dt,
            "status": "draft"
        }

        self.applications[user][app_id] = app
        return app_id

    def apps(self, user: str) -> list[dict]:
        """Return all applications for a user in order added."""
        if user not in self.applications:
            return []

        result = []
        for app_id in sorted(self.applications[user].keys(), key=lambda x: int(x)):
            app = self.applications[user][app_id]
            result.append({
                "id": app["id"],
                "company": app["company"],
                "deadline": app["deadline"].strftime("%m/%d %H:%M"),
                "status": app["status"]
            })
        return result

    def due_soon(self, user: str) -> list[dict]:
        """Return draft applications with deadline within 3 days, sorted by deadline."""
        if user not in self.applications:
            return []

        result = []
        now_date = self.now.date()
        three_days_later = now_date + timedelta(days=3)

        for app_id, app in self.applications[user].items():
            if app["status"] != "draft":
                continue

            deadline_dt = app["deadline"]
            days_diff = self._days_between_dates(now_date, deadline_dt.date())

            # Include if deadline is today or within 3 days from now
            # and deadline has not passed (deadline time >= now, or just check date?)
            # "締切がもう過ぎたものは入れません" - exclude passed deadlines
            # Interpretation: if deadline is before now (even same day), exclude if time has passed
            if deadline_dt < self.now:
                continue

            if deadline_dt.date() <= three_days_later:
                result.append({
                    "id": app["id"],
                    "company": app["company"],
                    "deadline": deadline_dt.strftime("%m/%d %H:%M"),
                    "status": app["status"]
                })

        # Sort by deadline (earliest first)
        result.sort(key=lambda x: x["deadline"])
        return result

    def tick(self) -> list[tuple[str, str]]:
        """Send notifications at 21:00 every day for due_soon applications."""
        if self.now.hour != 21 or self.now.minute != 0:
            return []

        notifications = []
        for user, apps_dict in self.applications.items():
            due_soon_list = self.due_soon(user)
            for app_info in due_soon_list:
                notifications.append((user, app_info["company"]))

        return notifications

    def move(self, user: str, app_id: str, to: str) -> None:
        """Move application status, with validation."""
        if user not in self.applications or app_id not in self.applications[user]:
            raise ValueError("Application not found or user does not own it")

        app = self.applications[user][app_id]
        lock = self._get_app_lock(app_id)

        with lock:
            current_status = app["status"]

            # Validate state transitions
            valid_transitions = {
                "draft": ["submitted"],
                "submitted": ["passed", "failed"],
                "passed": ["failed"],  # failed takes priority
                "failed": []  # final state
            }

            if to not in valid_transitions.get(current_status, []):
                # Special case: if already failed, passed is allowed but ignored
                if current_status == "failed" and to == "passed":
                    return
                raise ValueError(f"Cannot move from {current_status} to {to}")

            app["status"] = to

    def color(self, status: str) -> str:
        """Return color for a status."""
        colors = {
            "draft": "orange",
            "submitted": "blue",
            "passed": "green",
            "failed": "gray"
        }
        return colors.get(status, "gray")

    def extract_deadline(self, mail: str) -> Optional[str]:
        """Extract deadline from email body as 'M/D H:MM' format."""
        # Convert full-width characters to half-width
        mail = self._to_half_width(mail)

        # Pattern: month/day hour:minute
        # Handles flexible spacing and context
        pattern = r'(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})'
        match = re.search(pattern, mail)

        if match:
            month, day, hour, minute = match.groups()
            return f"{int(month)}/{int(day)} {int(hour)}:{minute}"

        return None

    def _to_half_width(self, text: str) -> str:
        """Convert full-width digits and symbols to half-width."""
        # Full-width to half-width mapping
        mapping = {
            '０': '0', '１': '1', '２': '2', '３': '3', '４': '4',
            '５': '5', '６': '6', '７': '7', '８': '8', '９': '9',
            '／': '/', '：': ':', '（': '(', '）': ')'
        }

        result = []
        for char in text:
            result.append(mapping.get(char, char))

        return ''.join(result)
