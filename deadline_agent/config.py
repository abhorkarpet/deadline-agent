import os
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
    since_days: int = 60
    max_messages: int = 1000
    debug: bool = False
    use_gmail_api: bool = False
    use_llm_extraction: bool = False
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"  # or gpt-4, claude-3-haiku, etc.
    oauth_client_secret_path: str = ""
    oauth_token_path: str = "token.json"
    oauth_scopes: tuple = ("https://www.googleapis.com/auth/gmail.readonly",)

    @staticmethod
    def from_env(prefix: str = "DA_") -> "AgentConfig":
        return AgentConfig(
            imap_host=os.getenv(f"{prefix}IMAP_HOST", "imap.gmail.com"),
            imap_port=int(os.getenv(f"{prefix}IMAP_PORT", "993")),
            email_address=os.getenv(f"{prefix}EMAIL_ADDRESS", ""),
            email_username=os.getenv(f"{prefix}EMAIL_USERNAME", os.getenv(f"{prefix}EMAIL_ADDRESS", "")),
            email_password=os.getenv(f"{prefix}EMAIL_PASSWORD", ""),
            mailbox=os.getenv(f"{prefix}MAILBOX", "INBOX"),
            since_days=int(os.getenv(f"{prefix}SINCE_DAYS", "60")),
            max_messages=int(os.getenv(f"{prefix}MAX_MESSAGES", "1000")),
            debug=os.getenv(f"{prefix}DEBUG", "0") in ("1", "true", "True"),
            use_gmail_api=os.getenv(f"{prefix}USE_GMAIL_API", "0") in ("1", "true", "True"),
            use_llm_extraction=os.getenv(f"{prefix}USE_LLM_EXTRACTION", "0") in ("1", "true", "True"),
            llm_api_key=os.getenv(f"{prefix}LLM_API_KEY", ""),
            llm_model=os.getenv(f"{prefix}LLM_MODEL", "gpt-4o-mini"),
            oauth_client_secret_path=os.getenv(f"{prefix}OAUTH_CLIENT_SECRET_PATH", ""),
            oauth_token_path=os.getenv(f"{prefix}OAUTH_TOKEN_PATH", "token.json"),
            oauth_scopes=tuple(
                (os.getenv(f"{prefix}OAUTH_SCOPES", "https://www.googleapis.com/auth/gmail.readonly").split(","))
            ),
        )


