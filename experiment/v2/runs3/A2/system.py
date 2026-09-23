from datetime import datetime, timedelta
import re
import threading
from collections import defaultdict

class System:
    def __init__(self, now: datetime):
        self.now = now
        self.data = defaultdict(dict)  # user -> app_id -> app_data
        self.ids = defaultdict(list)  # user -> [app_ids in insertion order]
        self.counter = 0
        self.mutex = threading.Lock()

    def set_now(self, now: datetime) -> None:
        self.now = now

    def add(self, user: str, company: str, deadline: str) -> str:
        with self.mutex:
            app_id = f"id_{self.counter}"
            self.counter += 1

            self.data[user][app_id] = {
                "company": company,
                "deadline": deadline,
                "status": "draft"
            }
            self.ids[user].append(app_id)
            return app_id

    def apps(self, user: str) -> list[dict]:
        with self.mutex:
            result = []
            for app_id in self.ids.get(user, []):
                app_data = self.data[user][app_id]
                result.append({
                    "id": app_id,
                    "company": app_data["company"],
                    "deadline": app_data["deadline"],
                    "status": app_data["status"]
                })
            return result

    def due_soon(self, user: str) -> list[dict]:
        with self.mutex:
            candidates = []

            for app_id in self.ids.get(user, []):
                app_data = self.data[user][app_id]

                if app_data["status"] != "draft":
                    continue

                deadline_obj = self._parse_deadline(app_data["deadline"])
                if deadline_obj is None:
                    continue

                # Within 3 days: now < deadline <= now + 3 days at 23:59
                deadline_threshold = self.now + timedelta(days=3)
                deadline_threshold = deadline_threshold.replace(hour=23, minute=59, second=59)

                if self.now < deadline_obj <= deadline_threshold:
                    candidates.append({
                        "id": app_id,
                        "company": app_data["company"],
                        "deadline": app_data["deadline"],
                        "status": app_data["status"],
                        "_sort_key": deadline_obj
                    })

            # Sort by deadline
            candidates.sort(key=lambda x: x["_sort_key"])

            # Remove sort key
            for item in candidates:
                del item["_sort_key"]

            return candidates

    def _parse_deadline(self, deadline: str) -> datetime | None:
        parts = deadline.split()
        if len(parts) != 2:
            return None

        try:
            month, day = map(int, parts[0].split('/'))
            hour, minute = map(int, parts[1].split(':'))
            year = self.now.year
            return datetime(year, month, day, hour, minute)
        except (ValueError, IndexError):
            return None

    def tick(self) -> list[tuple[str, str]]:
        if self.now.hour != 21 or self.now.minute != 0:
            return []

        result = []

        with self.mutex:
            for user in self.data:
                due_list = self.due_soon(user)
                for app in due_list:
                    result.append((user, app["company"]))

        return result

    def move(self, user: str, app_id: str, to: str) -> None:
        with self.mutex:
            if user not in self.data or app_id not in self.data[user]:
                raise ValueError("Application not found")

            app = self.data[user][app_id]
            current = app["status"]

            # State machine
            valid_transitions = {
                "draft": {"submitted"},
                "submitted": {"passed", "failed"},
                "passed": {"failed"},
                "failed": set()
            }

            if to not in valid_transitions[current]:
                if current == "failed" and to == "passed":
                    # Failed takes priority over passed - do nothing
                    return
                raise ValueError(f"Invalid transition from {current} to {to}")

            app["status"] = to

    def color(self, status: str) -> str:
        color_map = {
            "draft": "orange",
            "submitted": "blue",
            "passed": "green",
            "failed": "gray"
        }
        return color_map.get(status, "gray")

    def extract_deadline(self, mail: str) -> str | None:
        # Normalize full-width to half-width
        text = self._to_half_width(mail)

        # Find pattern: digit(s)/digit(s) space digit(s):digit(s)
        pattern = r'(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})'
        m = re.search(pattern, text)

        if m:
            return f"{m.group(1)}/{m.group(2)} {m.group(3)}:{m.group(4)}"

        return None

    def _to_half_width(self, text: str) -> str:
        # Map full-width Unicode digits and symbols
        mapping = {
            '０': '0', '１': '1', '２': '2', '３': '3', '４': '4',
            '５': '5', '６': '6', '７': '7', '８': '8', '９': '9',
            '／': '/', '：': ':', '（': '(', '）': ')'
        }

        result = []
        for c in text:
            result.append(mapping.get(c, c))

        return ''.join(result)
