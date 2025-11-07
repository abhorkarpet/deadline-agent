from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional
import uuid


@dataclass
class CalendarEventRequest:
    title: str
    starts_at: datetime
    duration_minutes: int = 30
    description: Optional[str] = None


class CalendarService:
    """Placeholder calendar service for future Google/Apple integrations."""

    def create_event(self, req: CalendarEventRequest) -> str:
        # Stub: return a fake event ID/URL
        iso = req.starts_at.isoformat()
        return f"calendar://event/{iso}/{req.title}"

    @staticmethod
    def generate_ics(events: Iterable[CalendarEventRequest], reminder_minutes_before: int = 0) -> str:
        def dtfmt(dt: datetime) -> str:
            # Use UTC and Zulu format; if naive, assume UTC
            if dt.tzinfo is None:
                return dt.strftime("%Y%m%dT%H%M%SZ")
            return dt.astimezone(tz=None).strftime("%Y%m%dT%H%M%SZ")

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//DeadlineAgent//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
        ]

        now_str = dtfmt(datetime.utcnow())
        for e in events:
            dtstart = e.starts_at
            dtend = e.starts_at + timedelta(minutes=e.duration_minutes)
            uid = f"{uuid.uuid4()}@deadline-agent"
            lines += [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now_str}",
                f"DTSTART:{dtfmt(dtstart)}",
                f"DTEND:{dtfmt(dtend)}",
                f"SUMMARY:{e.title}",
            ]
            if e.description:
                # Escape commas and semicolons minimally
                desc = e.description.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
                lines.append(f"DESCRIPTION:{desc}")

            if reminder_minutes_before and reminder_minutes_before > 0:
                trigger_minutes = int(reminder_minutes_before)
                lines += [
                    "BEGIN:VALARM",
                    "ACTION:DISPLAY",
                    f"TRIGGER:-PT{trigger_minutes}M",
                    "DESCRIPTION:Reminder",
                    "END:VALARM",
                ]

            lines.append("END:VEVENT")

        lines.append("END:VCALENDAR")
        return "\r\n".join(lines) + "\r\n"


