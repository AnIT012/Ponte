from datetime import datetime, timedelta
import re
import threading

# Q: For "3日以内" (within 3 days), interpreting as: from current time to end-of-day (23:59)
#    of the date 3 days from now. Example: 9/21 21:00 → includes deadlines up to 9/24 23:59.
# Q: Thread safety: using per-application locks for move() operations to prevent concurrent
#    modifications to the same application. Each app gets a unique lock created atomically.
# Q: For tick(), checking if hour==21 and minute==0. Returns list of (user, company) tuples
#    for all due-soon applications at that moment, one tuple per application.
# Q: For extract_deadline(), if multiple matches found, returning None (ambiguous).
#    Converting full-width to half-width digits and symbols before pattern matching.
#    Output format preserves variable-length month/day/hour but always 2-digit minutes.

class System:
    def __init__(self, now: datetime):
        self.now = now
        self.applications = {}  # user -> list of app dicts
        self.next_id = 0
        self.lock = threading.Lock()
        self.app_locks = {}  # app_id -> threading.Lock for per-app thread safety

    def set_now(self, now: datetime) -> None:
        with self.lock:
            self.now = now

    def add(self, user: str, company: str, deadline: str) -> str:
        """Add a new application and return its id.
        deadline format: "9/24 23:59" (month/day hour:minute, year is current year)
        """
        with self.lock:
            app_id = str(self.next_id)
            self.next_id += 1

            if user not in self.applications:
                self.applications[user] = []

            deadline_dt = self._parse_deadline(deadline)

            app = {
                "id": app_id,
                "company": company,
                "deadline": deadline,
                "deadline_dt": deadline_dt,
                "status": "draft"
            }

            self.applications[user].append(app)
            self.app_locks[app_id] = threading.Lock()

            return app_id

    def _parse_deadline(self, deadline_str: str) -> datetime:
        """Parse deadline string 'M/D H:MM' to datetime using current year."""
        parts = deadline_str.split()
        date_parts = parts[0].split("/")
        time_parts = parts[1].split(":")

        month = int(date_parts[0])
        day = int(date_parts[1])
        hour = int(time_parts[0])
        minute = int(time_parts[1])
        year = self.now.year

        return datetime(year, month, day, hour, minute)

    def apps(self, user: str) -> list[dict]:
        """Return all applications for user in order added."""
        with self.lock:
            if user not in self.applications:
                return []
            return [
                {
                    "id": app["id"],
                    "company": app["company"],
                    "deadline": app["deadline"],
                    "status": app["status"]
                }
                for app in self.applications[user]
            ]

    def _get_due_soon_internal(self, user: str) -> list[dict]:
        """Internal method to get due-soon applications (assumes lock is held).
        Returns list with deadline_dt for sorting purposes.
        """
        if user not in self.applications:
            return []

        due_apps = []
        now = self.now
        three_days_later = now + timedelta(days=3)
        three_days_end = three_days_later.replace(hour=23, minute=59, second=59)

        for app in self.applications[user]:
            if app["status"] == "draft":
                deadline_dt = app["deadline_dt"]
                # Deadline must be in the future and within 3 days
                if now < deadline_dt <= three_days_end:
                    due_apps.append({
                        "id": app["id"],
                        "company": app["company"],
                        "deadline": app["deadline"],
                        "status": app["status"],
                        "deadline_dt": deadline_dt
                    })

        due_apps.sort(key=lambda x: x["deadline_dt"])
        return due_apps

    def due_soon(self, user: str) -> list[dict]:
        """Return user's applications with nearby deadlines (draft status, within 3 days),
        sorted by earliest deadline first.
        """
        with self.lock:
            due_apps = self._get_due_soon_internal(user)
            return [
                {
                    "id": app["id"],
                    "company": app["company"],
                    "deadline": app["deadline"],
                    "status": app["status"]
                }
                for app in due_apps
            ]

    def tick(self) -> list[tuple[str, str]]:
        """If current time is 21:00, return list of (user, company) for all due-soon
        applications to notify. Otherwise return empty list.
        """
        with self.lock:
            if self.now.hour != 21 or self.now.minute != 0:
                return []

            notifications = []
            for user in self.applications:
                due_apps = self._get_due_soon_internal(user)
                for app in due_apps:
                    notifications.append((user, app["company"]))

            return notifications

    def move(self, user: str, app_id: str, to: str) -> None:
        """Change application status. Raises ValueError if invalid transition or
        application doesn't belong to user.

        Valid transitions:
        - draft → submitted
        - submitted → passed or failed
        - passed → failed (failed has priority)
        - failed → passed is allowed but stays failed (no error)
        """
        # Find app and verify ownership (with lock)
        app = None
        with self.lock:
            if user not in self.applications:
                raise ValueError(f"User {user} not found")

            for a in self.applications[user]:
                if a["id"] == app_id:
                    app = a
                    break

            if app is None:
                raise ValueError(f"Application {app_id} does not belong to user {user}")

        # Use per-app lock for thread-safe status modification
        with self.app_locks[app_id]:
            current = app["status"]

            if current == "draft":
                if to != "submitted":
                    raise ValueError(f"Cannot move from {current} to {to}")
            elif current == "submitted":
                if to not in ["passed", "failed"]:
                    raise ValueError(f"Cannot move from {current} to {to}")
            elif current == "passed":
                if to != "failed":
                    raise ValueError(f"Cannot move from {current} to {to}")
            elif current == "failed":
                if to == "passed":
                    return  # Stay in failed state (failed has priority)
                else:
                    raise ValueError(f"Cannot move from {current} to {to}")
            else:
                raise ValueError(f"Unknown status {current}")

            app["status"] = to

    def color(self, status: str) -> str:
        """Return color for a given status."""
        colors = {
            "draft": "orange",
            "submitted": "blue",
            "passed": "green",
            "failed": "gray"
        }
        return colors.get(status, "gray")

    def extract_deadline(self, mail: str) -> str | None:
        """Extract deadline from email body.

        Returns format "M/D H:MM" if exactly one deadline found.
        Returns None if zero matches, multiple matches (ambiguous), or if unsure.
        Converts full-width digits/symbols to half-width before extraction.
        """
        # Convert full-width to half-width
        mail = self._to_half_width(mail)

        # Pattern: month/day hour:minute (single or double digits for month/day/hour, 2 for minute)
        pattern = r'(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})'
        matches = re.findall(pattern, mail)

        if len(matches) == 0:
            return None
        elif len(matches) == 1:
            month, day, hour, minute = matches[0]
            return f"{int(month)}/{int(day)} {int(hour)}:{minute}"
        else:
            # Multiple matches - ambiguous, return None
            return None

    def _to_half_width(self, text: str) -> str:
        """Convert full-width digits and symbols to half-width."""
        zen_digit = "０１２３４５６７８９"
        han_digit = "0123456789"
        zen_symbols = {
            "（": "(",
            "）": ")",
            "／": "/",
            "：": ":"
        }

        result = []
        for char in text:
            if char in zen_digit:
                result.append(han_digit[zen_digit.index(char)])
            elif char in zen_symbols:
                result.append(zen_symbols[char])
            else:
                result.append(char)

        return "".join(result)
