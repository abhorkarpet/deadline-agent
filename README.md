# Deadline Agent

An intelligent email scanning agent that helps you track cancellation deadlines, subscription renewals, and refund deadlines from your inbox.

## Features

- 📧 **Email Integration**: Connect via IMAP (Gmail, Yahoo, etc.) with app passwords
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

Then open your browser to `http://localhost:8501`

### CLI Demo

```bash
python deadline_agent_demo.py
```

Set environment variables:
- `DA_EMAIL_ADDRESS`: Your email address
- `DA_EMAIL_PASSWORD`: Your app password (not regular password!)
- `DA_IMAP_HOST`: IMAP server (default: `imap.gmail.com`)
- `DA_IMAP_PORT`: IMAP port (default: `993`)
- `DA_MAILBOX`: Mailbox to scan (default: `INBOX`)
- `DA_SINCE_DAYS`: How many days back to scan (default: `60`)
- `DA_MAX_MESSAGES`: Max messages to process (default: `1000`)
- `DA_DEBUG`: Set to `1` for verbose output
- `DA_USE_LLM_EXTRACTION`: Set to `1` to enable LLM extraction
- `DA_LLM_API_KEY`: Your OpenAI API key (if using LLM)
- `DA_LLM_MODEL`: Model to use (default: `gpt-4o-mini`)

## Getting an App Password

### Gmail
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

