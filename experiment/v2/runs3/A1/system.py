# Q: When adding a deadline like "9/24 23:59" while in October, the year is assumed to be the current year. If the deadline date has already passed this year (e.g., adding "9/24 23:59" on 10/1), it will be a past deadline.
# Q: The tick() method sends notifications only once per day when called at 21:00. Multiple calls to tick() at 21:00 on the same day will only send notifications on the first call.
# Q: Full-width characters (０-９, ／, ：, （, ）) are converted to half-width equivalents. Other full-width symbols are not handled.
# Q: The extract_deadline() method returns the first deadline pattern found. If multiple patterns exist with "or"/"または" between them (ambiguous), it returns None. Otherwise, multiple patterns without "or" between them result in the first one being returned.

from datetime import datetime, timedelta
import re
import threading
from collections import defaultdict
from uuid import uuid4

class System:
    def __init__(self, now: datetime):
        self.now = now
        self.applications = defaultdict(dict)
        self.lock = threading.RLock()
        self._last_notification_day = None

    def set_now(self, now: datetime) -> None:
        """Change current time (for testing)"""
        with self.lock:
            self.now = now

    def add(self, user: str, company: str, deadline: str) -> str:
        """Add application and return id. deadline is "M/D H:MM" format"""
        with self.lock:
            # Parse deadline string "M/D H:MM"
            parts = deadline.split()
            date_part = parts[0]  # "9/24"
            time_part = parts[1]  # "23:59"

            month, day = map(int, date_part.split('/'))
            hour, minute = map(int, time_part.split(':'))

            # Use current year
            deadline_dt = datetime(self.now.year, month, day, hour, minute)

            # Generate ID
            app_id = str(uuid4())

            self.applications[user][app_id] = {
                "company": company,
                "deadline": deadline_dt,
                "status": "draft"
            }

            return app_id

    def apps(self, user: str) -> list[dict]:
        """Return all user's applications in add order"""
        with self.lock:
            result = []
            for app_id, app_data in self.applications[user].items():
                result.append({
                    "id": app_id,
                    "company": app_data["company"],
                    "deadline": self._format_deadline(app_data["deadline"]),
                    "status": app_data["status"]
                })
            return result

    def due_soon(self, user: str) -> list[dict]:
        """Return approaching deadline applications (earliest first)"""
        with self.lock:
            result = []
            three_days_later = self.now + timedelta(days=3)
            three_days_end = datetime(
                three_days_later.year,
                three_days_later.month,
                three_days_later.day,
                23, 59, 59
            )

            for app_id, app_data in self.applications[user].items():
                if app_data["status"] == "draft" and self.now < app_data["deadline"] <= three_days_end:
                    result.append({
                        "id": app_id,
                        "company": app_data["company"],
                        "deadline": self._format_deadline(app_data["deadline"]),
                        "status": app_data["status"]
                    })

            # Sort by deadline
            result.sort(key=lambda x: x["deadline"])
            return result

    def tick(self) -> list[tuple[str, str]]:
        """Send notifications at 21:00, return [(owner, company)] in order"""
        with self.lock:
            if self.now.hour != 21 or self.now.minute != 0:
                return []

            current_day = self.now.date()

            # Check if we already notified today
            if self._last_notification_day == current_day:
                return []

            self._last_notification_day = current_day

            notifications = []

            # For each user, get their due soon applications
            for user in self.applications.keys():
                three_days_later = self.now + timedelta(days=3)
                three_days_end = datetime(
                    three_days_later.year,
                    three_days_later.month,
                    three_days_later.day,
                    23, 59, 59
                )

                # Collect due applications
                due_apps = []
                for app_id, app_data in self.applications[user].items():
                    if app_data["status"] == "draft" and self.now < app_data["deadline"] <= three_days_end:
                        due_apps.append((app_data["deadline"], app_data["company"]))

                # Sort by deadline
                due_apps.sort()

                # Add notifications
                for deadline, company in due_apps:
                    notifications.append((user, company))

            return notifications

    def move(self, user: str, app_id: str, to: str) -> None:
        """Change status. Raise ValueError if invalid."""
        with self.lock:
            if user not in self.applications or app_id not in self.applications[user]:
                raise ValueError("Application not found")

            app = self.applications[user][app_id]
            current_status = app["status"]

            # Special case: failed takes priority
            if current_status == "failed":
                # Stay failed, don't change to passed
                return

            # Check valid transitions
            valid_transitions = {
                "draft": ["submitted"],
                "submitted": ["passed", "failed"],
                "passed": ["failed"]
            }

            if to not in valid_transitions.get(current_status, []):
                raise ValueError(f"Invalid transition from {current_status} to {to}")

            app["status"] = to

    def color(self, status: str) -> str:
        """Return color for status"""
        colors = {
            "draft": "orange",
            "submitted": "blue",
            "passed": "green",
            "failed": "gray"
        }
        return colors.get(status, "gray")

    def extract_deadline(self, mail: str) -> str | None:
        """Extract deadline from email in M/D H:MM format"""
        # Convert full-width numbers and symbols to half-width
        mail = self._fullwidth_to_halfwidth(mail)

        # Look for pattern M/D H:MM
        pattern = r'(\d{1,2})/(\d{1,2})\D*?(\d{1,2}):(\d{2})'
        matches = list(re.finditer(pattern, mail))

        if len(matches) == 0:
            return None
        elif len(matches) > 1:
            # Multiple matches - check if ambiguous (e.g., "X or Y")
            for i in range(len(matches) - 1):
                between = mail[matches[i].end():matches[i+1].start()]
                if re.search(r'(または|or)', between, re.IGNORECASE):
                    return None

        match = matches[0]
        month, day, hour, minute = match.groups()
        return f"{int(month)}/{int(day)} {int(hour)}:{minute}"

    def _format_deadline(self, dt: datetime) -> str:
        """Format datetime as M/D H:MM"""
        return f"{dt.month}/{dt.day} {dt.hour}:{dt.minute:02d}"

    def _fullwidth_to_halfwidth(self, text: str) -> str:
        """Convert full-width digits and symbols to half-width"""
        fullwidth_nums = '０１２３４５６７８９'
        halfwidth_nums = '0123456789'

        for i in range(10):
            text = text.replace(fullwidth_nums[i], halfwidth_nums[i])

        # Convert full-width symbols
        text = text.replace('／', '/')
        text = text.replace('：', ':')
        text = text.replace('（', '(')
        text = text.replace('）', ')')

        return text
