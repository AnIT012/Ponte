import re
from datetime import datetime, timedelta
from threading import Lock
from collections import defaultdict

class System:
    def __init__(self, now: datetime):
        self.now = now
        self.applications = {}
        self.user_apps = defaultdict(list)
        self.next_id = 0
        self.lock = Lock()

    def set_now(self, now: datetime) -> None:
        self.now = now

    def add(self, user: str, company: str, deadline: str) -> str:
        with self.lock:
            app_id = str(self.next_id)
            self.next_id += 1

            deadline_dt = self._parse_deadline(deadline)

            self.applications[app_id] = {
                'user': user,
                'company': company,
                'deadline': deadline_dt,
                'status': 'draft'
            }
            self.user_apps[user].append(app_id)
            return app_id

    def apps(self, user: str) -> list[dict]:
        with self.lock:
            result = []
            for app_id in self.user_apps[user]:
                app = self.applications[app_id]
                result.append({
                    'id': app_id,
                    'company': app['company'],
                    'deadline': self._format_deadline(app['deadline']),
                    'status': app['status']
                })
            return result

    def due_soon(self, user: str) -> list[dict]:
        with self.lock:
            result = []
            for app_id in self.user_apps[user]:
                app = self.applications[app_id]
                if app['status'] == 'draft' and self._is_within_3_days(app['deadline']):
                    result.append({
                        'id': app_id,
                        'company': app['company'],
                        'deadline': app['deadline'],
                        'status': app['status']
                    })
            result.sort(key=lambda x: x['deadline'])
            result = [{
                'id': item['id'],
                'company': item['company'],
                'deadline': self._format_deadline(item['deadline']),
                'status': item['status']
            } for item in result]
            return result

    def tick(self) -> list[tuple[str, str]]:
        if self.now.hour != 21 or self.now.minute != 0:
            return []

        result = []
        with self.lock:
            for user, app_ids in self.user_apps.items():
                for app_id in app_ids:
                    app = self.applications[app_id]
                    if app['status'] == 'draft' and self._is_within_3_days(app['deadline']):
                        result.append((user, app['company']))
        return result

    def move(self, user: str, app_id: str, to: str) -> None:
        with self.lock:
            if app_id not in self.applications:
                raise ValueError(f"Application {app_id} not found")

            app = self.applications[app_id]
            if app['user'] != user:
                raise ValueError(f"User {user} cannot access application {app_id}")

            current = app['status']

            if current == 'failed':
                if to == 'passed':
                    return
                elif to == 'failed':
                    return
                else:
                    raise ValueError(f"Cannot move from {current} to {to}")

            if current == 'passed':
                if to == 'failed':
                    app['status'] = 'failed'
                elif to == 'passed':
                    return
                else:
                    raise ValueError(f"Cannot move from {current} to {to}")

            if current == 'submitted':
                if to in ['passed', 'failed']:
                    app['status'] = to
                elif to == 'submitted':
                    return
                else:
                    raise ValueError(f"Cannot move from {current} to {to}")

            if current == 'draft':
                if to == 'submitted':
                    app['status'] = 'submitted'
                elif to == 'draft':
                    return
                else:
                    raise ValueError(f"Cannot move from {current} to {to}")

            raise ValueError(f"Unknown status {current}")

    def color(self, status: str) -> str:
        colors = {
            'draft': 'orange',
            'submitted': 'blue',
            'passed': 'green',
            'failed': 'gray'
        }
        return colors.get(status, 'gray')

    def extract_deadline(self, mail: str) -> str | None:
        mail = self._convert_fullwidth_to_halfwidth(mail)

        pattern = r'\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2}'
        matches = re.findall(pattern, mail)

        if len(matches) == 1:
            return matches[0]

        return None

    def _parse_deadline(self, deadline: str) -> datetime:
        parts = deadline.split()
        date_parts = parts[0].split('/')
        time_parts = parts[1].split(':')

        month = int(date_parts[0])
        day = int(date_parts[1])
        hour = int(time_parts[0])
        minute = int(time_parts[1])

        return datetime(self.now.year, month, day, hour, minute)

    def _format_deadline(self, deadline: datetime) -> str:
        return f"{deadline.month}/{deadline.day} {deadline.hour}:{deadline.minute:02d}"

    def _is_within_3_days(self, deadline: datetime) -> bool:
        if deadline <= self.now:
            return False

        three_days_later = self.now + timedelta(days=3)
        three_days_later = three_days_later.replace(hour=23, minute=59, second=59, microsecond=0)

        return deadline <= three_days_later

    def _convert_fullwidth_to_halfwidth(self, text: str) -> str:
        result = []
        for char in text:
            if '０' <= char <= '９':
                result.append(chr(ord(char) - 0xFEE0))
            elif char == '（':
                result.append('(')
            elif char == '）':
                result.append(')')
            elif char == '／':
                result.append('/')
            elif char == '：':
                result.append(':')
            else:
                result.append(char)
        return ''.join(result)
