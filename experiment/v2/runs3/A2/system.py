from datetime import datetime, timedelta
import re
import threading

# Q: Applications stored in-memory with no persistence across restarts
# Q: Thread-safe using per-user locks for concurrent access
# Q: Deadline returned as string in "月/日 時:分" format (without leading zeros)
# Q: "3 days within" means from now (exclusive) to 3 days later at 23:59 (inclusive)
# Q: extract_deadline returns None if zero or multiple matches found (user confirmation needed)
# Q: Full-width digits/symbols converted to half-width for email parsing
# Q: Notification at 21:00 means exactly hour=21 and minute=0

class System:
    def __init__(self, now: datetime):
        self.now = now
        self.users = {}  # user -> {"apps": [app_dict], "lock": threading.Lock()}

    def set_now(self, now: datetime) -> None:
        """Update current time (for testing)"""
        self.now = now

    def _ensure_user(self, user: str):
        """Ensure user exists in the system"""
        if user not in self.users:
            self.users[user] = {"apps": [], "lock": threading.Lock()}

    def add(self, user: str, company: str, deadline: str) -> str:
        """
        Add new application and return its ID.
        deadline format: "月/日 時:分" like "9/24 23:59" (year is current year)
        """
        self._ensure_user(user)

        # Parse deadline "9/24 23:59"
        parts = deadline.split()
        date_part = parts[0]  # "9/24"
        time_part = parts[1]  # "23:59"

        month, day = map(int, date_part.split('/'))
        hour, minute = map(int, time_part.split(':'))

        deadline_dt = datetime(self.now.year, month, day, hour, minute)

        with self.users[user]["lock"]:
            app_id = str(len(self.users[user]["apps"]))
            app = {
                "id": app_id,
                "company": company,
                "deadline": deadline_dt,
                "status": "draft"
            }
            self.users[user]["apps"].append(app)
            return app_id

    def apps(self, user: str) -> list[dict]:
        """Return all applications for user in order added"""
        self._ensure_user(user)

        with self.users[user]["lock"]:
            result = []
            for app in self.users[user]["apps"]:
                result.append({
                    "id": app["id"],
                    "company": app["company"],
                    "deadline": self._format_deadline(app["deadline"]),
                    "status": app["status"]
                })
            return result

    def due_soon(self, user: str) -> list[dict]:
        """
        Return draft applications with deadline within 3 days,
        sorted by deadline (earliest first)
        """
        self._ensure_user(user)

        # Calculate 3-day cutoff: now + 3 days at 23:59
        three_days_later = self.now + timedelta(days=3)
        cutoff = three_days_later.replace(hour=23, minute=59, second=59)

        with self.users[user]["lock"]:
            # Filter: draft status and deadline in future and within cutoff
            due = []
            for app in self.users[user]["apps"]:
                if (app["status"] == "draft" and
                    self.now < app["deadline"] <= cutoff):
                    due.append(app)

            # Sort by deadline (earliest first)
            due.sort(key=lambda x: x["deadline"])

            result = []
            for app in due:
                result.append({
                    "id": app["id"],
                    "company": app["company"],
                    "deadline": self._format_deadline(app["deadline"]),
                    "status": app["status"]
                })
            return result

    def tick(self) -> list[tuple[str, str]]:
        """
        If current time is 21:00, send notifications for due_soon applications.
        Return list of (user, company) pairs that were notified.
        """
        if self.now.hour != 21 or self.now.minute != 0:
            return []

        notifications = []
        for user in self.users:
            due = self.due_soon(user)
            for app in due:
                notifications.append((user, app["company"]))

        return notifications

    def move(self, user: str, app_id: str, to: str) -> None:
        """
        Change application status.
        Raises ValueError if transition is invalid or application not found/not user's.

        Valid transitions:
        - draft -> submitted
        - submitted -> passed or failed
        - passed -> failed (failed takes priority)
        - failed -> (final state, no transition)
        """
        self._ensure_user(user)

        with self.users[user]["lock"]:
            # Find application
            app = None
            for a in self.users[user]["apps"]:
                if a["id"] == app_id:
                    app = a
                    break

            if app is None:
                raise ValueError(f"Application {app_id} not found for user {user}")

            current = app["status"]

            # Validate and apply transition
            if current == "draft" and to == "submitted":
                app["status"] = "submitted"
            elif current == "submitted" and to in ["passed", "failed"]:
                app["status"] = to
            elif current == "passed" and to == "failed":
                # Failed overrides passed (priority rule)
                app["status"] = "failed"
            elif current == "failed" and to == "passed":
                # Failed is final, passed does not override it
                pass
            else:
                raise ValueError(f"Cannot move from {current} to {to}")

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
        """
        Extract deadline from email body.
        Input: email text (may contain full-width digits/symbols)
        Output: "月/日 時:分" format like "10/15 12:00", or None if not found/ambiguous

        Examples:
        - "10/15(木)12:00まで" -> "10/15 12:00"
        - "【締切9/24 23:59】" -> "9/24 23:59"
        - "来週中にご提出ください" -> None (not found)
        - "9/24 23:59 または 9/30 23:59" -> None (ambiguous: 2 matches)
        """
        # Convert full-width digits and symbols to half-width
        normalized = self._to_half_width(mail)

        # Pattern: month/day hour:minute
        # Matches: 1-2 digits / 1-2 digits space(s) 1-2 digits : 2 digits
        pattern = r'(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})'
        matches = re.findall(pattern, normalized)

        # Must have exactly one match (ambiguous or not found -> None)
        if len(matches) != 1:
            return None

        month, day, hour, minute = matches[0]
        # Remove leading zeros by converting to int and back to str
        month_str = str(int(month))
        day_str = str(int(day))
        hour_str = str(int(hour))
        # Keep minute as-is (preserve "00" if present, but "09" becomes "9")
        minute_str = str(int(minute))

        return f"{month_str}/{day_str} {hour_str}:{minute_str}"

    def _format_deadline(self, dt: datetime) -> str:
        """Format datetime as "月/日 時:分" without leading zeros"""
        month = str(dt.month)
        day = str(dt.day)
        hour = str(dt.hour)
        minute = f"{dt.minute:02d}"
        return f"{month}/{day} {hour}:{minute}"

    def _to_half_width(self, text: str) -> str:
        """Convert full-width digits and symbols to half-width"""
        # Full-width digits: U+FF10 to U+FF19
        for i in range(10):
            full_char = chr(0xFF10 + i)
            half_char = str(i)
            text = text.replace(full_char, half_char)

        # Common full-width symbols
        text = text.replace('／', '/')  # Full-width slash
        text = text.replace('：', ':')  # Full-width colon
        text = text.replace('（', '(')  # Full-width parenthesis left
        text = text.replace('）', ')')  # Full-width parenthesis right

        return text
