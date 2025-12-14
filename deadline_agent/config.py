import os
from datetime import date, datetime, timedelta
from dataclasses import dataclass

# Force reload - v2

@dataclass
class AgentConfig:
    imap_host: str
    imap_port: int
    email_address: str
    email_username: str
    email_password: str
    mailbox: str = "INBOX"
    # Mutually exclusive scan window:
    # - scan_window_mode == "days": use since_days
    # - scan_window_mode == "start_date": use since_start_date (YYYY-MM-DD, local midnight)
    scan_window_mode: str = "days"  # "days" | "start_date"
    since_days: int = 7
    since_start_date: str = ""  # YYYY-MM-DD
    max_messages: int = 1000
    debug: bool = False
    use_gmail_api: bool = False  # Deprecated: use auth_method instead
    use_llm_extraction: bool = False
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"  # or gpt-4, claude-3-haiku, etc.
    # OAuth configuration
    auth_method: str = "oauth"  # "oauth" | "imap" - auto-detected for Gmail
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    oauth_redirect_uri: str = ""  # Auto-detect: local vs Streamlit Cloud
    oauth_token_storage: str = "session"  # "session" | "file" - "session" for Streamlit, "file" for CLI
    oauth_client_secret_path: str = ""  # Legacy: path to client_secret.json file
    oauth_token_path: str = "token.json"
    oauth_scopes: tuple = ("https://www.googleapis.com/auth/gmail.readonly",)

    def is_gmail(self) -> bool:
        """Check if email address is Gmail."""
        if not self.email_address:
            return False
        email_lower = self.email_address.lower()
        return email_lower.endswith(("@gmail.com", "@googlemail.com"))

    def get_default_auth_method(self) -> str:
        """Get default auth method based on email provider."""
        if self.is_gmail():
            return "oauth"
        return "imap"

    def effective_since_date_local(self) -> date:
        """
        Compute the effective local-date cutoff used for scanning.
        - days mode: today - since_days
        - start_date mode: parse since_start_date (YYYY-MM-DD)
        Falls back to days mode on invalid input.
        """
        mode = (self.scan_window_mode or "days").strip().lower()
        if mode == "start_date" and self.since_start_date:
            try:
                return datetime.strptime(self.since_start_date.strip(), "%Y-%m-%d").date()
            except Exception:
                # fall back to days mode
                pass
        # Default: days
        try:
            days = int(self.since_days)
        except Exception:
            days = 60
        return (datetime.now() - timedelta(days=days)).date()

    @staticmethod
    def from_env(prefix: str = "DA_") -> "AgentConfig":
        email_address = os.getenv(f"{prefix}EMAIL_ADDRESS", "")
        config = AgentConfig(
            imap_host=os.getenv(f"{prefix}IMAP_HOST", "imap.gmail.com"),
            imap_port=int(os.getenv(f"{prefix}IMAP_PORT", "993")),
            email_address=email_address,
            email_username=os.getenv(f"{prefix}EMAIL_USERNAME", email_address),
            email_password=os.getenv(f"{prefix}EMAIL_PASSWORD", ""),
            mailbox=os.getenv(f"{prefix}MAILBOX", "INBOX"),
            scan_window_mode=os.getenv(f"{prefix}SCAN_WINDOW_MODE", "days"),
            since_days=int(os.getenv(f"{prefix}SINCE_DAYS", "7")),
            since_start_date=os.getenv(f"{prefix}SINCE_START_DATE", ""),
            max_messages=int(os.getenv(f"{prefix}MAX_MESSAGES", "1000")),
            debug=os.getenv(f"{prefix}DEBUG", "0") in ("1", "true", "True"),
            use_gmail_api=os.getenv(f"{prefix}USE_GMAIL_API", "0") in ("1", "true", "True"),
            use_llm_extraction=os.getenv(f"{prefix}USE_LLM_EXTRACTION", "0") in ("1", "true", "True"),
            llm_api_key=os.getenv(f"{prefix}LLM_API_KEY", ""),
            llm_model=os.getenv(f"{prefix}LLM_MODEL", "gpt-4o-mini"),
            auth_method=os.getenv(f"{prefix}AUTH_METHOD", ""),  # Will be auto-set if empty
            oauth_client_id=os.getenv(f"{prefix}OAUTH_CLIENT_ID", ""),
            oauth_client_secret=os.getenv(f"{prefix}OAUTH_CLIENT_SECRET", ""),
            oauth_redirect_uri=os.getenv(f"{prefix}OAUTH_REDIRECT_URI", ""),
            oauth_token_storage=os.getenv(f"{prefix}OAUTH_TOKEN_STORAGE", "file"),  # Default to file for CLI
            oauth_client_secret_path=os.getenv(f"{prefix}OAUTH_CLIENT_SECRET_PATH", ""),
            oauth_token_path=os.getenv(f"{prefix}OAUTH_TOKEN_PATH", "token.json"),
            oauth_scopes=tuple(
                (os.getenv(f"{prefix}OAUTH_SCOPES", "https://www.googleapis.com/auth/gmail.readonly").split(","))
            ),
        )
        # Auto-detect auth_method if not set
        if not config.auth_method:
            config.auth_method = config.get_default_auth_method()
        return config


