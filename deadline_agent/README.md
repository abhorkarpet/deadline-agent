## Deadline Agent

An agent that scans your email for cancellation/refund deadlines (free trials, subscription renewals, fully-refundable travel, etc.), and lists upcoming deadlines sorted by date. Initial version uses IMAP (works with Gmail/Yahoo and most providers with app passwords). Calendar integrations are stubbed for future work.

### Quick start

1. Create an app password for your email provider (recommended). For Gmail, enable IMAP and use an App Password.
2. Set environment variables:

```
export DA_EMAIL_ADDRESS="your@email"
export DA_EMAIL_PASSWORD="your-app-password"
# Optional overrides
export DA_IMAP_HOST="imap.gmail.com"
export DA_IMAP_PORT=993
export DA_MAILBOX="INBOX"
export DA_SINCE_DAYS=60
export DA_MAX_MESSAGES=1000
```

3. Install dependencies:

```
pip install -r requirements.txt
```

4. Run demo:

```
python examples/deadline_agent_demo.py
```

### Use Gmail OAuth (no IMAP password)

1. Create OAuth credentials in Google Cloud Console (Desktop App). Download `client_secret.json`.
2. Set env vars and run with Gmail API:

```
export DA_USE_GMAIL_API=1
export DA_OAUTH_CLIENT_SECRET_PATH="/absolute/path/to/client_secret.json"
export DA_OAUTH_TOKEN_PATH="/absolute/path/to/token.json"  # created on first run
python examples/deadline_agent_demo.py
```

The first run opens a browser to authorize read-only Gmail access and stores a token for subsequent runs.

### Notes

- This version avoids OAuth complexity by using IMAP with username/password (prefer app passwords). OAuth-based Gmail and provider-specific integrations can be added later.
- Deadline extraction is heuristic-based using regex + natural date parsing. It can be expanded with provider-specific parsers and ML later.
- Calendar creation is stubbed in `deadline_agent/calendar.py`.


