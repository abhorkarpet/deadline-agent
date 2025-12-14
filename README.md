# Deadline Agent

An intelligent email scanning agent that helps you track cancellation deadlines, subscription renewals, and refund deadlines from your inbox.

## Features

- 📧 **Email Integration**: 
  - **Gmail OAuth** (recommended): Connect with Google - no app passwords needed!
  - **IMAP**: Connect via IMAP for Gmail (fallback) or other providers (Yahoo, etc.) with app passwords
- 🤖 **AI-Powered Extraction**: Uses both regex patterns and LLM (OpenAI) for accurate deadline detection
- 📅 **Calendar Integration**: Export deadlines as `.ics` files for your calendar
- 🎯 **Smart Categorization**: Automatically categorizes deadlines (subscription, trial, travel, billing, refund)
- 📊 **Feedback Learning**: Improves accuracy over time based on your feedback
- 💰 **Cost Tracking**: Shows estimated costs and usage for LLM extraction

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

### Web UI (Recommended)

```bash
streamlit run deadline_agent_app.py
```

Then open your browser to `http://localhost:8501` (or the port shown in terminal)

### Gmail OAuth Setup (Recommended for Gmail Users)

**For Gmail users, OAuth is the recommended authentication method** - it's more secure and doesn't require app passwords!

1. **Create Google OAuth Credentials**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Enable the **Gmail API**:
     - Go to "APIs & Services" > "Library"
     - Search for "Gmail API" and enable it
   - Create OAuth 2.0 credentials:
     - Go to "APIs & Services" > "Credentials"
     - Click "Create Credentials" > "OAuth client ID"
     - Application type: **Web application**
     - Authorized redirect URIs:
       - Local: `http://localhost:8501/oauth_callback` (or your port)
       - Streamlit Cloud: `https://your-app.streamlit.app/oauth_callback`
     - Click "Create" and copy the **Client ID** and **Client Secret**

2. **Add Credentials to Streamlit**:
   - **Option A**: Use Streamlit secrets (recommended for Streamlit Cloud)
     - Create `.streamlit/secrets.toml`:
       ```toml
       gmail_oauth_client_id = "your-client-id"
       gmail_oauth_client_secret = "your-client-secret"
       ```
   - **Option B**: Enter in UI
     - In the sidebar, expand "OAuth Credentials (Advanced)"
     - Enter your Client ID and Client Secret

3. **Connect**:
   - Enter your Gmail address
   - Click "🔗 Connect with Google"
   - Authorize the app in the browser
   - You're connected! ✅

**Note**: OAuth tokens are stored in session state (secure, not exposed to frontend). For CLI usage, tokens are stored in a file.

### CLI Demo

```bash
python deadline_agent_demo.py
```

Set environment variables:

**Email Configuration**:
- `DA_EMAIL_ADDRESS`: Your email address
- `DA_AUTH_METHOD`: Authentication method: `oauth` (default for Gmail) or `imap` (default for others)
- `DA_EMAIL_PASSWORD`: Your app password (required for IMAP, not needed for OAuth)
- `DA_OAUTH_CLIENT_ID`: Google OAuth Client ID (for Gmail OAuth)
- `DA_OAUTH_CLIENT_SECRET`: Google OAuth Client Secret (for Gmail OAuth)
- `DA_IMAP_HOST`: IMAP server (default: `imap.gmail.com`)
- `DA_IMAP_PORT`: IMAP port (default: `993`)
- `DA_MAILBOX`: Mailbox to scan (default: `INBOX`)

**Scan Configuration**:
- `DA_SCAN_WINDOW_MODE`: Scan window mode: `days` or `start_date` (default: `days`)
- `DA_SINCE_DAYS`: How many days back to scan (default: `7`) — used when `DA_SCAN_WINDOW_MODE=days`
- `DA_SINCE_START_DATE`: Start date `YYYY-MM-DD` (local time) — used when `DA_SCAN_WINDOW_MODE=start_date`
- `DA_MAX_MESSAGES`: Max messages to process (default: `1000`)
- `DA_DEBUG`: Set to `1` for verbose output

**LLM Configuration** (Optional):
- `DA_USE_LLM_EXTRACTION`: Set to `1` to enable LLM extraction
- `DA_LLM_API_KEY`: Your OpenAI API key (if using LLM)
- `DA_LLM_MODEL`: Model to use (default: `gpt-4o-mini`)

## Getting an App Password (IMAP Fallback)

**For Gmail users**: We recommend using **OAuth** (see above) instead of app passwords. App passwords are only needed if you choose to use IMAP instead of OAuth.

### Gmail (IMAP)
1. Go to [Google Account](https://myaccount.google.com/)
2. Click **Security** (left sidebar)
3. Under "How you sign in to Google", click **2-Step Verification**
4. Scroll down to find **App passwords** (or search for it)
5. Click **App passwords** > Select app: **Mail** > Select device: **Other (Custom name)**
6. Enter a name (e.g., "Deadline Agent") and click **Generate**
7. Copy the 16-character password (shown only once)

**Note:** If you don't see "App passwords", you may need to enable 2-Step Verification first.

### Yahoo
1. Go to [Account Security](https://login.yahoo.com/account/security)
2. Click **Generate app password**
3. Select "Mail" and generate
4. Copy the password

## Usage

### Basic Usage (Regex Only - Free)

The agent can work with just regex patterns, which is free but less accurate:

```python
from deadline_agent import AgentConfig, DeadlineAgent

config = AgentConfig.from_env()
agent = DeadlineAgent(config)
deadlines, stats = agent.collect_deadlines()

for deadline in deadlines:
    print(f"{deadline.deadline_at}: {deadline.title}")
```

### Advanced Usage (With LLM - Paid)

Enable LLM extraction for better accuracy on invoices, varied phrasing, etc.:

```python
config = AgentConfig.from_env()
config.use_llm_extraction = True
config.llm_api_key = "your-openai-api-key"
config.llm_model = "gpt-4o-mini"  # or gpt-4o, gpt-4-turbo

agent = DeadlineAgent(config)
deadlines, stats = agent.collect_deadlines()
```

## Cost Estimates

- **gpt-4o-mini**: ~$0.0003 per email (very cheap)
- **gpt-4o**: ~$0.003 per email
- **gpt-4-turbo**: ~$0.01 per email

Check your actual usage at [OpenAI Usage](https://platform.openai.com/usage)

## Project Structure

```
deadline-agent/
├── deadline_agent/          # Core package
│   ├── __init__.py
│   ├── agent.py            # Main agent orchestrator
│   ├── config.py           # Configuration management
│   ├── email_client.py     # IMAP email client
│   ├── llm_extractor.py   # LLM-based extraction
│   ├── parsers.py          # Regex-based extraction
│   ├── models.py           # Data models
│   ├── calendar.py         # Calendar export (.ics)
│   ├── feedback_learner.py # Learning from feedback
│   └── gmail_api_client.py # Gmail OAuth (optional)
├── deadline_agent_app.py   # Streamlit web UI
├── deadline_agent_demo.py  # CLI demo
├── requirements.txt
└── README.md
```

## License

See LICENSE file for details.

