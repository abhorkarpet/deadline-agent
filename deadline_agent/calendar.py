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
            # Escape title for .ics format
            title_escaped = e.title.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", " ").replace("\r", "")
            
            lines += [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now_str}",
                f"DTSTART:{dtfmt(dtstart)}",
                f"DTEND:{dtfmt(dtend)}",
                f"SUMMARY:{title_escaped}",
            ]
            if e.description:
                # Remove emojis and other non-ASCII characters that can cause encoding issues
                import re
                # Remove emojis but keep the text
                desc_clean = re.sub(r'[^\x00-\x7F]+', '', e.description)
                
                # Properly escape special characters for .ics format (RFC 5545)
                # Order matters: escape backslashes first, then other special chars
                desc = desc_clean.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
                # Convert actual newlines to escaped newlines for .ics format
                desc = desc.replace("\n", "\\n").replace("\r", "")
                
                # Fold long lines according to RFC 5545: max 75 chars per line
                # Continuation lines start with a single space
                prefix = "DESCRIPTION:"
                max_line_len = 75
                first_line_max = max_line_len - len(prefix)  # Should be 63
                
                # Fold the description
                if len(desc) <= first_line_max:
                    # Fits on one line
                    lines.append(f"{prefix}{desc}")
                else:
                    # First line
                    lines.append(f"{prefix}{desc[:first_line_max]}")
                    remaining = desc[first_line_max:]
                    # Continuation lines (start with space, max 74 chars to keep total at 75)
                    while len(remaining) > 0:
                        if len(remaining) <= 74:
                            lines.append(f" {remaining}")
                            break
                        else:
                            lines.append(f" {remaining[:74]}")
                            remaining = remaining[74:]

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


