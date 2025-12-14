from __future__ import annotations

import base64
import json
import os
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow, InstalledAppFlow
from googleapiclient.discovery import build

from .config import AgentConfig
from .models import EmailMessageData


class GmailAPIClient:
    def __init__(self, config: AgentConfig, credentials: Optional[Credentials] = None):
        self.config = config
        self._credentials = credentials
        self.service = None
        if credentials:
            self.service = self._build_service(credentials)
        elif config.oauth_token_storage == "session":
            # For Streamlit with session storage, don't authorize here
            # Will use get_authorization_url() and handle_oauth_callback() instead
            pass
        elif config.oauth_client_id and config.oauth_client_secret:
            # Have client_id/secret but no credentials yet - don't authorize here
            # Will use get_authorization_url() for OAuth flow
            pass
        else:
            # Try file-based authorization (CLI mode)
            self.service = self._authorize()

    def _build_service(self, creds: Credentials):
        """Build Gmail service from credentials."""
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    def _authorize(self):
        """Authorize using file-based token storage (CLI mode)."""
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
                # Try new direct client_id/secret approach first
                if self.config.oauth_client_id and self.config.oauth_client_secret:
                    # For Streamlit, we don't authorize here - use get_authorization_url instead
                    # This method is only called for CLI/file-based auth
                    # Return None service - will be set via set_credentials later
                    return None
                # Fallback to old file-based flow for CLI
                elif self.config.oauth_client_secret_path and os.path.exists(self.config.oauth_client_secret_path):
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.config.oauth_client_secret_path,
                        scopes=list(self.config.oauth_scopes),
                    )
                    creds = flow.run_local_server(port=0)
                else:
                    # Don't raise error here - allow lazy initialization for Streamlit
                    return None
            if self.config.oauth_token_path and creds:
                with open(self.config.oauth_token_path, "w") as token:
                    token.write(creds.to_json())

        if creds:
            self._credentials = creds
            return self._build_service(creds)
        return None

    def get_authorization_url(self, redirect_uri: str) -> Tuple[str, str]:
        """
        Generate OAuth authorization URL for user to visit.
        Returns (authorization_url, state) tuple.
        """
        if not self.config.oauth_client_id or not self.config.oauth_client_secret:
            raise ValueError("OAuth client ID and secret are required. Please configure them in the UI or env vars.")

        # Create flow for web application
        client_config = {
            "web": {
                "client_id": self.config.oauth_client_id,
                "client_secret": self.config.oauth_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        }

        flow = Flow.from_client_config(
            client_config,
            scopes=list(self.config.oauth_scopes),
            redirect_uri=redirect_uri,
        )
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",  # Force consent to get refresh token
        )
        return authorization_url, state

    def handle_oauth_callback(self, code: str, redirect_uri: str) -> Credentials:
        """
        Exchange authorization code for tokens.
        Returns Credentials object.
        """
        if not self.config.oauth_client_id or not self.config.oauth_client_secret:
            raise ValueError("OAuth client ID and secret are required.")

        client_config = {
            "web": {
                "client_id": self.config.oauth_client_id,
                "client_secret": self.config.oauth_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        }

        flow = Flow.from_client_config(
            client_config,
            scopes=list(self.config.oauth_scopes),
            redirect_uri=redirect_uri,
        )
        flow.fetch_token(code=code)
        creds = flow.credentials

        # Store credentials based on storage type
        if self.config.oauth_token_storage == "file" and self.config.oauth_token_path:
            with open(self.config.oauth_token_path, "w") as token:
                token.write(creds.to_json())

        self._credentials = creds
        self.service = self._build_service(creds)
        return creds

    def set_credentials(self, creds: Credentials):
        """Set credentials (for Streamlit session state)."""
        self._credentials = creds
        self.service = self._build_service(creds)

    def get_credentials(self) -> Optional[Credentials]:
        """Get current credentials."""
        return self._credentials

    def is_authenticated(self) -> bool:
        """Check if valid tokens exist."""
        if not self._credentials:
            return False
        if not self._credentials.valid:
            if self._credentials.expired and self._credentials.refresh_token:
                try:
                    self._credentials.refresh(Request())
                    self.service = self._build_service(self._credentials)
                    return True
                except Exception:
                    return False
            return False
        return True

    def revoke_access(self):
        """Revoke OAuth tokens."""
        if self._credentials:
            try:
                self._credentials.revoke(Request())
            except Exception:
                pass
        self._credentials = None
        self.service = None

    def ensure_authenticated(self):
        """Ensure service is authenticated and ready. Raises if not."""
        if not self.service:
            if not self._credentials:
                raise ValueError("Not authenticated. Please connect with Google first.")
            if not self.is_authenticated():
                raise ValueError("OAuth token expired. Please reconnect.")

    def fetch_recent_messages(self) -> List[EmailMessageData]:
        """Fetch recent messages. Ensures authentication before making API calls."""
        self.ensure_authenticated()
        
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



