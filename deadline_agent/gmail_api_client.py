from __future__ import annotations

import base64
from datetime import datetime
from typing import List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .config import AgentConfig
from .models import EmailMessageData


class GmailAPIClient:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.service = self._authorize()

    def _authorize(self):
        creds: Optional[Credentials] = None
        if self.config.oauth_token_path:
            try:
                creds = Credentials.from_authorized_user_file(
                    self.config.oauth_token_path, list(self.config.oauth_scopes)
                )
            except Exception:
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.config.oauth_client_secret_path,
                    scopes=list(self.config.oauth_scopes),
                )
                creds = flow.run_local_server(port=0)
            if self.config.oauth_token_path:
                with open(self.config.oauth_token_path, "w") as token:
                    token.write(creds.to_json())

        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    def fetch_recent_messages(self) -> List[EmailMessageData]:
        # Mutually exclusive scan window:
        # - days mode: newer_than:Nd
        # - start_date mode: after:YYYY/MM/DD
        mode = (self.config.scan_window_mode or "days").strip().lower()
        if mode == "start_date":
            cutoff = self.config.effective_since_date_local()
            query_parts = [f"after:{cutoff.strftime('%Y/%m/%d')}"]
        else:
            query_parts = [f"newer_than:{self.config.since_days}d"]
        # Focus labels: INBOX by default
        label_ids = [self.config.mailbox] if self.config.mailbox else ["INBOX"]

        results = (
            self.service.users()
            .messages()
            .list(userId="me", q=" ".join(query_parts), labelIds=label_ids, maxResults=self.config.max_messages)
            .execute()
        )
        messages = results.get("messages", [])
        items: List[EmailMessageData] = []

        for m in messages:
            msg = (
                self.service.users().messages().get(userId="me", id=m["id"], format="full").execute()
            )
            headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
            subject = headers.get("subject", "")
            sender = headers.get("from", "")
            date_header = headers.get("date")
            parsed_date: Optional[datetime] = None
            if date_header:
                try:
                    import email as _pyemail

                    parsed_date = _pyemail.utils.parsedate_to_datetime(date_header)
                except Exception:
                    parsed_date = None
            parsed_date = parsed_date or datetime.utcnow()

            text_body = self._get_body_by_mime(msg.get("payload", {}), "text/plain") or ""
            html_body = self._get_body_by_mime(msg.get("payload", {}), "text/html")

            items.append(
                EmailMessageData(
                    uid=msg.get("id", ""),
                    subject=subject,
                    sender=sender,
                    date=parsed_date,
                    text=text_body,
                    html=html_body,
                    source_mailbox="GMAIL_API",
                )
            )

        return items

    def _get_body_by_mime(self, payload: dict, mime: str) -> Optional[str]:
        if payload.get("mimeType") == mime and "data" in payload.get("body", {}):
            return self._decode(payload["body"]["data"]) or None

        for part in payload.get("parts", []) or []:
            if part.get("mimeType") == mime and "data" in part.get("body", {}):
                return self._decode(part["body"]["data"]) or None
            # multipart/alternative nesting
            if part.get("parts"):
                nested = self._get_body_by_mime(part, mime)
                if nested:
                    return nested
        return None

    @staticmethod
    def _decode(data: str) -> str:
        data = data.replace("-", "+").replace("_", "/")
        return base64.b64decode(data).decode("utf-8", errors="replace")



