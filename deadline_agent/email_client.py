import email
import imaplib
from datetime import datetime
from email.header import decode_header, make_header
from typing import Iterable, List, Optional

from .config import AgentConfig
from .models import EmailMessageData


class EmailClient:
    def __init__(self, config: AgentConfig):
        self.config = config

    def _connect(self) -> imaplib.IMAP4_SSL:
        conn = imaplib.IMAP4_SSL(self.config.imap_host, self.config.imap_port)
        try:
            conn.login(self.config.email_username, self.config.email_password)
        except imaplib.IMAP4.error as e:
            error_msg = str(e) if isinstance(e, str) else (e.decode('utf-8') if isinstance(e, bytes) else repr(e))
            if "Application-specific password" in error_msg or "185833" in error_msg:
                raise ValueError(
                    "❌ App password required! You're using your regular password. "
                    "Please generate an app password from your Google Account settings "
                    "(Security > 2-Step Verification > App passwords). "
                    "See the sidebar for detailed instructions."
                ) from e
            raise
        return conn

    def fetch_recent_messages(self) -> List[EmailMessageData]:
        conn = self._connect()
        try:
            status, _ = conn.select(self.config.mailbox)
            if status != "OK":
                return []

            since_date = self.config.effective_since_date_local().strftime("%d-%b-%Y")
            status, data = conn.search(None, "(SINCE", since_date + ")")
            if status != "OK" or not data or not data[0]:
                return []

            uids = data[0].split()
            if self.config.max_messages:
                uids = uids[-self.config.max_messages :]

            messages: List[EmailMessageData] = []
            for uid in uids:
                status, msg_data = conn.fetch(uid, "(RFC822)")
                if status != "OK" or not msg_data:
                    continue
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                subject = str(make_header(decode_header(msg.get("Subject", ""))))
                sender = str(make_header(decode_header(msg.get("From", ""))))

                date_header = msg.get("Date")
                parsed_date: Optional[datetime] = None
                if date_header:
                    try:
                        parsed_date = email.utils.parsedate_to_datetime(date_header)
                    except Exception:
                        parsed_date = None
                parsed_date = parsed_date or datetime.utcnow()

                text_body = None
                html_body = None

                if msg.is_multipart():
                    for part in msg.walk():
                        ctype = part.get_content_type()
                        disp = part.get("Content-Disposition", "")
                        if ctype == "text/plain" and "attachment" not in disp:
                            try:
                                text_body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                            except Exception:
                                text_body = None
                        elif ctype == "text/html" and "attachment" not in disp:
                            try:
                                html_body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                            except Exception:
                                html_body = None
                else:
                    ctype = msg.get_content_type()
                    payload = msg.get_payload(decode=True) or b""
                    try:
                        decoded = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
                    except Exception:
                        decoded = ""
                    if ctype == "text/plain":
                        text_body = decoded
                    elif ctype == "text/html":
                        html_body = decoded

                messages.append(
                    EmailMessageData(
                        uid=uid.decode("utf-8") if isinstance(uid, bytes) else str(uid),
                        subject=subject,
                        sender=sender,
                        date=parsed_date,
                        text=text_body or "",
                        html=html_body,
                        source_mailbox=self.config.mailbox,
                    )
                )

            return messages
        finally:
            try:
                conn.logout()
            except Exception:
                pass



