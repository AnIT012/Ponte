# Q: Applications are stored in-memory (dict by user), no persistence to disk
# Q: IDs are generated as incremental integers per user (uuid not needed per requirements)
# Q: "3 days" is interpreted as: today + 2 more days, so 3 calendar days total
# Q: Deadline extraction handles full-width characters by converting them to half-width
# Q: Thread-safe via threading.Lock on each application's state
# Q: If both passed and failed transitions arrive, failed wins (no error thrown)
# Q: Notifications at 21:00 check if any admin/system user has a pending notification queue

from datetime import datetime, timedelta
import re
import threading
import unicodedata

class System:
    def __init__(self, now: datetime):
        self.now = now
        self.apps_by_user = {}  # {user: {app_id: {...}}}
        self.next_id_per_user = {}  # {user: next_id}
        self.locks = {}  # {(user, app_id): Lock}
        self.global_lock = threading.Lock()
        self.notified_today = set()  # {(user, app_id)} to avoid duplicate notifications

    def set_now(self, now: datetime) -> None:
        self.now = now
        self.notified_today.clear()

    def add(self, user: str, company: str, deadline: str) -> str:
        # deadline format: "9/24 23:59"
        with self.global_lock:
            if user not in self.apps_by_user:
                self.apps_by_user[user] = {}
                self.next_id_per_user[user] = 1

            app_id = str(self.next_id_per_user[user])
            self.next_id_per_user[user] += 1

            # Parse deadline
            deadline_dt = self._parse_deadline_str(deadline)

            app = {
                "id": app_id,
                "company": company,
                "deadline": deadline_dt,
                "status": "draft",
                "created_at": self.now
            }

            self.apps_by_user[user][app_id] = app
            self.locks[(user, app_id)] = threading.Lock()

            return app_id

    def apps(self, user: str) -> list[dict]:
        with self.global_lock:
            if user not in self.apps_by_user:
                return []

            result = []
            for app_id in sorted(self.apps_by_user[user].keys(), key=lambda x: int(x)):
                app = self.apps_by_user[user][app_id]
                result.append({
                    "id": app["id"],
                    "company": app["company"],
                    "deadline": app["deadline"].strftime("%m/%d %H:%M"),
                    "status": app["status"]
                })
            return result

    def due_soon(self, user: str) -> list[dict]:
        with self.global_lock:
            if user not in self.apps_by_user:
                return []

            result = []
            now = self.now
            three_days_later = now + timedelta(days=3)

            for app_id, app in self.apps_by_user[user].items():
                if app["status"] == "draft":
                    deadline = app["deadline"]
                    # Check if deadline is within 3 days and not in the past
                    if now < deadline <= three_days_later:
                        result.append({
                            "id": app["id"],
                            "company": app["company"],
                            "deadline": deadline.strftime("%m/%d %H:%M"),
                            "status": app["status"]
                        })

            # Sort by deadline (earliest first)
            result.sort(key=lambda x: datetime.strptime(x["deadline"], "%m/%d %H:%M"))
            return result

    def tick(self) -> list[tuple[str, str]]:
        # Check if current time is 21:00
        if self.now.hour != 21 or self.now.minute != 0:
            return []

        notifications = []

        with self.global_lock:
            for user in self.apps_by_user:
                due_soon_apps = self.due_soon(user)
                for app in due_soon_apps:
                    app_id = app["id"]
                    key = (user, app_id)

                    # Avoid sending duplicate notifications on the same day
                    if key not in self.notified_today:
                        notifications.append((user, app["company"]))
                        self.notified_today.add(key)

        return notifications

    def move(self, user: str, app_id: str, to: str) -> None:
        with self.global_lock:
            if user not in self.apps_by_user or app_id not in self.apps_by_user[user]:
                raise ValueError(f"Application {app_id} not found for user {user}")

            app = self.apps_by_user[user][app_id]

        # Get the app-specific lock
        key = (user, app_id)
        if key not in self.locks:
            with self.global_lock:
                self.locks[key] = threading.Lock()

        with self.locks[key]:
            current = app["status"]

            # Validate state transition
            if current == to:
                return  # No change needed

            if current == "draft":
                if to not in ["submitted"]:
                    raise ValueError(f"Cannot move from {current} to {to}")
            elif current == "submitted":
                if to not in ["passed", "failed"]:
                    raise ValueError(f"Cannot move from {current} to {to}")
            elif current == "passed":
                # If already passed, only accept failed (failed has priority)
                if to == "failed":
                    app["status"] = to
                elif to != "passed":
                    raise ValueError(f"Cannot move from {current} to {to}")
                return
            elif current == "failed":
                # If already failed, stay failed
                if to != "failed":
                    return  # Ignore other transitions
            else:
                raise ValueError(f"Unknown status {current}")

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
        # Convert full-width characters to half-width
        normalized = self._normalize_full_to_half(mail)

        # Look for patterns like "9/24 23:59" or "10/15 12:00"
        # Month/Day Hour:Minute
        pattern = r'(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})'

        matches = re.findall(pattern, normalized)

        # If multiple matches or no matches, return None
        if len(matches) != 1:
            return None

        month, day, hour, minute = matches[0]

        # Validate ranges
        month_int = int(month)
        day_int = int(day)
        hour_int = int(hour)
        minute_int = int(minute)

        if not (1 <= month_int <= 12):
            return None
        if not (1 <= day_int <= 31):
            return None
        if not (0 <= hour_int <= 23):
            return None
        if not (0 <= minute_int <= 59):
            return None

        return f"{month_int}/{day_int} {hour_int}:{minute_int:02d}"

    def _normalize_full_to_half(self, text: str) -> str:
        # Convert full-width digits to half-width
        result = []
        for char in text:
            if '０' <= char <= '９':  # Full-width digits
                result.append(chr(ord(char) - 0xfee0))
            elif char == '：':  # Full-width colon
                result.append(':')
            elif char == '／':  # Full-width slash
                result.append('/')
            elif char == '（':  # Full-width left paren
                result.append('(')
            elif char == '）':  # Full-width right paren
                result.append(')')
            else:
                result.append(char)
        return ''.join(result)

    def _parse_deadline_str(self, deadline: str) -> datetime:
        # deadline format: "9/24 23:59" with year from self.now
        parts = deadline.split()
        date_part = parts[0]
        time_part = parts[1]

        month, day = map(int, date_part.split('/'))
        hour, minute = map(int, time_part.split(':'))

        year = self.now.year
        return datetime(year, month, day, hour, minute)
