import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse, parse_qs

# Add current directory to path so we can import deadline_agent
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
from google.oauth2.credentials import Credentials

from deadline_agent import AgentConfig, DeadlineAgent, FeedbackLearner, InsufficientFundsError
from deadline_agent.calendar import CalendarEventRequest, CalendarService
from deadline_agent.gmail_api_client import GmailAPIClient


FEEDBACK_FILE = "deadline_agent_feedback.jsonl"
VERSION = "3.5"


def get_redirect_uri() -> str:
    """Get OAuth redirect URI based on current environment."""
    # Check if we're in Streamlit Cloud
    try:
        # Streamlit Cloud sets this environment variable
        if os.getenv("STREAMLIT_SERVER_BASE_URL"):
            base_url = os.getenv("STREAMLIT_SERVER_BASE_URL")
            return f"{base_url}/oauth_callback"
    except Exception:
        pass
    
    # Get port from Streamlit config or default
    try:
        import streamlit as st
        # Try to get port from query params or use default
        port = st.get_option("server.port") or 8501
    except Exception:
        port = 8501
    
    # Default to local with detected port
    return f"http://localhost:{port}/oauth_callback"


def handle_oauth_callback(cfg: AgentConfig) -> Optional[Credentials]:
    """Handle OAuth callback from query parameters."""
    query_params = st.query_params
    if "code" in query_params and "state" in query_params:
        code = query_params["code"]
        state = query_params["state"]
        
        try:
            client = GmailAPIClient(cfg)
            redirect_uri = get_redirect_uri()
            creds = client.handle_oauth_callback(code, redirect_uri)
            
            # Store in session state
            st.session_state['gmail_oauth_credentials'] = creds.to_json()
            st.session_state['gmail_oauth_email'] = cfg.email_address
            
            # Clear query params
            st.query_params.clear()
            st.rerun()
            return creds
        except Exception as e:
            st.error(f"OAuth authentication failed: {str(e)}")
            return None
    return None


def get_gmail_oauth_credentials(cfg: AgentConfig) -> Optional[Credentials]:
    """Get Gmail OAuth credentials from session state."""
    if 'gmail_oauth_credentials' in st.session_state:
        try:
            creds_json = st.session_state['gmail_oauth_credentials']
            creds = Credentials.from_authorized_user_info(json.loads(creds_json))
            # Refresh if expired
            if creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
                st.session_state['gmail_oauth_credentials'] = creds.to_json()
            return creds
        except Exception:
            # Clear invalid credentials
            if 'gmail_oauth_credentials' in st.session_state:
                del st.session_state['gmail_oauth_credentials']
    return None


def get_config_from_ui() -> AgentConfig:
    st.sidebar.markdown("### Email Configuration")
    
    # Get email from session state (persisted across OAuth redirects) or env var
    # Streamlit automatically stores widget values in session state when a key is provided
    default_email = (
        st.session_state.get('email_address_input', "") or
        st.session_state.get('gmail_oauth_email', "") or
        os.getenv("DA_EMAIL_ADDRESS", "")
    )
    
    email_address = st.sidebar.text_input(
        "Email address",
        value=default_email,
        key="email_address_input"
    )
    
    # Note: Streamlit automatically stores the value in st.session_state['email_address_input']
    # when the widget has a key, so we don't need to manually set it
    
    # Always use IMAP (OAuth removed)
    auth_method = "imap"
    
    # App password instructions
    is_gmail = email_address.lower().endswith(("@gmail.com", "@googlemail.com")) if email_address else False
    if is_gmail:
        with st.sidebar.expander("💡 How to get an app password", expanded=False):
            st.markdown("""
            **⚠️ IMPORTANT: This is NOT your regular Gmail password!**
            
            You must generate a special "app password" - a 16-character code that allows apps to access your email securely.
            
            1. Go to [Google Account](https://myaccount.google.com/)
            2. Click **Security** (left sidebar)
            3. Under "How you sign in to Google", click **2-Step Verification**
            4. Scroll down to find **App passwords** (or search for it)
            5. Click **App passwords** > Select app: **Mail** > Select device: **Other (Custom name)**
            6. Enter a name (e.g., "Deadline Agent") and click **Generate**
            7. Copy the 16-character password (shown only once) - this is your app password
            
            **Note:** If you don't see "App passwords", you may need to enable 2-Step Verification first.
            """)
    else:
        with st.sidebar.expander("💡 How to get an app password", expanded=False):
            st.markdown("""
            **For Yahoo:**
            1. Go to [Account Security](https://login.yahoo.com/account/security)
            2. Click **Generate app password**
            3. Select "Mail" and generate
            4. Copy the password
            
            **Other providers:** Check your email provider's help docs for app password setup.
            """)
    
    email_password = st.sidebar.text_input(
        "Email app password", 
        type="password", 
        value=os.getenv("DA_EMAIL_PASSWORD", ""), 
        help="App password for your email provider"
    )
    
    # IMAP settings - hidden in Advanced section
    with st.sidebar.expander("⚙️ Advanced IMAP Settings", expanded=False):
        imap_host = st.text_input("IMAP host", value=os.getenv("DA_IMAP_HOST", "imap.gmail.com"))
        imap_port = st.number_input("IMAP port", value=int(os.getenv("DA_IMAP_PORT", "993")))
        mailbox = st.text_input("Mailbox", value=os.getenv("DA_MAILBOX", "INBOX"))
    
    # Mutually exclusive scan window
    scan_window_mode = st.sidebar.radio(
        "Scan window",
        options=["Last N days", "Start date"],
        index=0,
        help="Choose either a rolling window (last N days) or a specific start date.",
    )

    since_days_default = int(os.getenv("DA_SINCE_DAYS", "7"))
    since_days = since_days_default
    since_start_date_str = os.getenv("DA_SINCE_START_DATE", "")

    if scan_window_mode == "Last N days":
        since_days = st.sidebar.number_input(
            "Last N days",
            min_value=1,
            max_value=365,
            value=since_days_default,
            help="Scan emails from the last N days. For example, 7 means scan emails from the past week."
        )
        since_start_date = ""
        scan_window_mode_cfg = "days"
    else:
        # Default start date: env var if present, else today - 7 days
        default_start = date.today() - timedelta(days=7)
        if since_start_date_str:
            try:
                default_start = datetime.strptime(since_start_date_str.strip(), "%Y-%m-%d").date()
            except Exception:
                default_start = default_start
        picked = st.sidebar.date_input(
            "Start date",
            value=default_start,
            help="Emails received on/after this date will be scanned (local time).",
        )
        since_start_date = picked.strftime("%Y-%m-%d")
        scan_window_mode_cfg = "start_date"

    with st.sidebar.expander("Advanced", expanded=False):
        max_messages = st.number_input(
            "Max messages (safety cap)",
            min_value=10,
            max_value=5000,
            value=int(os.getenv("DA_MAX_MESSAGES", "500")),
            help="Stops scanning after this many messages, even if the date window would include more.",
        )
    debug_mode = st.sidebar.toggle("🔍 Debug/Verbose mode", value=False, help="Show detailed scan statistics")
    
    st.sidebar.divider()
    st.sidebar.markdown("### 🤖 LLM Extraction (Optional)")
    st.sidebar.caption("Use AI to find deadlines in invoices, renewal notices, and varied phrasing")
    use_llm = st.sidebar.toggle("Enable LLM extraction", value=False, help="Requires OpenAI API key. More accurate but costs money (~$0.01 per 100 emails)")
    llm_api_key = ""
    llm_model = "gpt-4o-mini"
    if use_llm:
        llm_api_key = st.sidebar.text_input(
            "OpenAI API Key", 
            type="password", 
            value=os.getenv("DA_LLM_API_KEY", ""), 
            help="Get your API key from https://platform.openai.com/api-keys. You'll need to create an account and add a payment method."
        )
        llm_model = st.sidebar.selectbox("Model", ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"], index=0, help="gpt-4o-mini is cheapest and sufficient")
    
    # OAuth removed - no longer needed
    
    return AgentConfig(
        imap_host=imap_host,
        imap_port=int(imap_port),
        email_address=email_address,
        email_username=email_address,
        email_password=email_password,
        mailbox=mailbox,
        scan_window_mode=scan_window_mode_cfg,
        since_days=int(since_days),
        since_start_date=since_start_date,
        max_messages=int(max_messages),
        auth_method="imap",  # Always use IMAP (OAuth removed)
        oauth_client_id="",  # Not used (OAuth removed)
        oauth_client_secret="",  # Not used (OAuth removed)
        oauth_redirect_uri="",  # Not used (OAuth removed)
        oauth_token_storage="session",  # Not used (OAuth removed)
        use_gmail_api=False,  # OAuth removed, always use IMAP
        debug=debug_mode,
        use_llm_extraction=use_llm,
        llm_api_key=llm_api_key,
        llm_model=llm_model,
    )


def store_feedback(item, reason: str):
    record = {
        "deadline_at": item.deadline_at.isoformat(),
        "title": item.title,
        "source": item.source,
        "reason": reason,
        "ts": datetime.utcnow().isoformat(),
    }
    try:
        with open(FEEDBACK_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
        # Clear feedback learner cache so it picks up new feedback
        learner = FeedbackLearner(FEEDBACK_FILE)
        learner.clear_cache()
    except Exception:
        pass


def main():
    # Set page config (must be first Streamlit command)
    st.set_page_config(
        page_title="Deadline Agent",
        page_icon="⏰",  # Alarm clock emoji as favicon
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("Deadline Agent")
    st.caption("Authenticate, scan inbox for deadlines, review results, and create reminders")
    
    # Browser recommendation - hide after first view
    if "hide_browser_tip" not in st.session_state:
        st.session_state.hide_browser_tip = False
    
    if not st.session_state.hide_browser_tip:
        browser_tip_container = st.container()
        with browser_tip_container:
            col1, col2 = st.columns([4, 1])
            with col1:
                st.info("💡 **Best experience:** Use Chrome browser on Desktop for optimal performance")
            with col2:
                if st.button("Dismiss", key="dismiss_browser_tip", use_container_width=True):
                    st.session_state.hide_browser_tip = True
                    st.rerun()

    # Render sidebar/config
    cfg = get_config_from_ui()

    # Optional Welcome / Onboarding
    # Initialize session state only once - these should persist across reruns
    if "suppress_welcome" not in st.session_state:
        st.session_state.suppress_welcome = False
    if "welcomed" not in st.session_state:
        st.session_state.welcomed = False
    
    # Ensure welcomed stays True once set - never reset it to False
    # This prevents the welcome from showing again after it's been dismissed

    # Get OAuth credentials from session state if available (cfg already loaded above)
    oauth_creds = get_gmail_oauth_credentials(cfg) if cfg.is_gmail() and cfg.auth_method == "oauth" else None

    def render_welcome():
        st.subheader("Welcome 👋")
        st.markdown(
            """
            This assistant helps you avoid surprise charges by finding cancellation/refund deadlines from your emails and creating calendar reminders.

            What it does:
            - Connects to your email via Gmail OAuth (recommended) or IMAP (Gmail, Yahoo, etc. with app password)
            - Scans recent messages for phrases like "free trial ends", "cancel by", "fully refundable until"
            - Lets you review and select the correct items, give feedback, and export reminders to your calendar (.ics)

            Privacy & security:
            - Your data stays local in your browser/session.
            - OAuth tokens (if any) are stored only in session state (secure, not exposed to frontend).
            - No messages are sent to any external server from this app.

            How to use:
            1) Enter your email address in the sidebar
            2) For Gmail: Click "Connect with Google" (OAuth - no password needed!)
            3) For other providers: Enter your app password
            4) Click "Authenticate & Scan"
            5) Review detected items, uncheck incorrect ones, and submit feedback if we mis-detected
            6) Click "Create Reminders" and download the .ics file
            """
        )
        # Use a separate state variable for the checkbox to avoid affecting suppress_welcome during reruns
        # Only update suppress_welcome when the button is clicked
        checkbox_key = "welcome_dont_show_checkbox"
        if checkbox_key not in st.session_state:
            st.session_state[checkbox_key] = st.session_state.suppress_welcome
        
        dont_show = st.checkbox("Don't show again", value=st.session_state[checkbox_key], key=checkbox_key)
        
        if st.button("I understand, continue →", key="welcome_continue"):
            # Only update suppress_welcome when button is clicked, not on checkbox interaction
            if dont_show:
                st.session_state.suppress_welcome = True
            else:
                st.session_state.suppress_welcome = False
            st.session_state.welcomed = True
            st.rerun()

    # Show welcome only if not suppressed and not yet welcomed
    # Once welcomed is True, it stays True for the session - this prevents showing welcome again on reruns
    should_show_welcome = not st.session_state.suppress_welcome and not st.session_state.welcomed
    if should_show_welcome:
        with st.container(border=True):
            render_welcome()
        # Don't stop - allow sidebar to remain visible
        st.stop()

    if "deadlines" not in st.session_state:
        st.session_state.deadlines = []
    if "selected" not in st.session_state:
        st.session_state.selected = set()
    if "scan_stats" not in st.session_state:
        st.session_state.scan_stats = None

    # Initialize confirmation skip state
    if "skip_scan_confirmation" not in st.session_state:
        st.session_state.skip_scan_confirmation = False
    if "fetched_email_count" not in st.session_state:
        st.session_state.fetched_email_count = None
    if "waiting_llm_confirmation" not in st.session_state:
        st.session_state.waiting_llm_confirmation = False
    if "skip_llm_for_scan" not in st.session_state:
        st.session_state.skip_llm_for_scan = False
    if "interrupt_scan" not in st.session_state:
        st.session_state.interrupt_scan = False
    if "fetched_emails" not in st.session_state:
        st.session_state.fetched_emails = None
    if "scan_in_progress" not in st.session_state:
        st.session_state.scan_in_progress = False
    
    # Function to fetch emails first (for cost estimation)
    def fetch_emails_for_cost(cfg):
        """Fetch emails to get actual count for cost estimation."""
        try:
            if not cfg.email_address:
                st.error("Please provide your email address in the sidebar.")
                return False
            
            # Check password (always using IMAP now)
            if not cfg.email_password:
                st.error("Please provide your email app password in the sidebar.")
                return False
            
            # Create agent with LLM disabled temporarily
            cfg_no_llm = AgentConfig(
                imap_host=cfg.imap_host,
                imap_port=cfg.imap_port,
                email_address=cfg.email_address,
                email_username=cfg.email_username,
                email_password=cfg.email_password,
                mailbox=cfg.mailbox,
                since_days=cfg.since_days,
                max_messages=cfg.max_messages,
                debug=cfg.debug,
                auth_method="imap",  # Always use IMAP (OAuth removed)
                oauth_client_id="",  # Not used (OAuth removed)
                oauth_client_secret="",  # Not used (OAuth removed)
                oauth_redirect_uri="",  # Not used (OAuth removed)
                oauth_token_storage="session",  # Not used (OAuth removed)
                use_gmail_api=False,  # OAuth removed
                use_llm_extraction=False,  # Disable LLM for initial fetch
                llm_api_key="",
                llm_model=cfg.llm_model,
                scan_window_mode=cfg.scan_window_mode,
                since_start_date=cfg.since_start_date,
            )
            # Create agent (always using IMAP now)
            agent = DeadlineAgent(cfg_no_llm)
            
            status_text = st.empty()
            status_text.text("Fetching emails...")
            
            messages = agent.fetch_emails_only()
            st.session_state.fetched_email_count = len(messages)
            status_text.empty()
            return True
        except Exception as e:
            status_text.empty()
            raise
    
    # Function to process pre-fetched emails
    def process_fetched_emails(cfg, messages, skip_llm=False):
        """Process already-fetched emails without reconnecting."""
        from deadline_agent.agent import ScanStats
        
        agent = DeadlineAgent(cfg)
        
        # Progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        interrupt_button_placeholder = st.empty()
        
        # Show interrupt button once at the start
        if not st.session_state.interrupt_scan:
            with interrupt_button_placeholder.container():
                if st.button("⏹️ Interrupt Analysis", key="interrupt_analysis_btn", type="secondary"):
                    st.session_state.interrupt_scan = True
                    st.rerun()
        
        def update_progress(message: str, progress: float):
            if st.session_state.interrupt_scan:
                raise KeyboardInterrupt("Scan interrupted by user")
            progress_bar.progress(progress)
            status_text.text(message)
        
        try:
            # Process emails directly
            update_progress(f"Processing {len(messages)} fetched emails...", 0.1)
            
            all_items = []
            senders = set()
            sample_subjects = []
            
            total = len(messages)
            batch_size = 100
            num_batches = (total + batch_size - 1) // batch_size
            
            for batch_idx in range(num_batches):
                if st.session_state.interrupt_scan:
                    raise KeyboardInterrupt("Analysis interrupted by user")
                
                start_idx = batch_idx * batch_size
                end_idx = min(start_idx + batch_size, total)
                batch = messages[start_idx:end_idx]
                
                if total > 0:
                    progress_pct = 0.1 + (start_idx / total) * 0.8
                    update_progress(f"Processing batch {batch_idx + 1}/{num_batches} (emails {start_idx + 1}-{end_idx}/{total})...", progress_pct)
                
                for msg in batch:
                    senders.add(msg.sender)
                    if len(sample_subjects) < 5:
                        sample_subjects.append(msg.subject[:60])
                    
                    # Try regex first
                    regex_items = agent.regex_extractor.extract_from_message(msg)
                    all_items.extend(regex_items)
                    
                    # Try LLM if enabled
                    if agent.llm_extractor and not skip_llm:
                        try:
                            llm_items = agent.llm_extractor.extract_from_message(msg)
                            all_items.extend(llm_items)
                        except Exception as e:
                            from deadline_agent.llm_extractor import InsufficientFundsError
                            if isinstance(e, InsufficientFundsError):
                                raise
                            if cfg.debug:
                                print(f"LLM extraction error for {msg.subject}: {e}")
            
            update_progress(f"Found {len(all_items)} potential deadlines. Applying filters...", 0.9)
            
            # Apply feedback-based filtering
            filtered_items = agent.feedback_learner.apply_feedback_learning(all_items)
            
            update_progress(f"Complete! Found {len(filtered_items)} deadlines.", 1.0)
            
            stats = ScanStats(
                emails_fetched=len(messages),
                emails_processed=len(messages),
                deadlines_found=len(filtered_items),
                unique_senders=len(senders),
                sample_subjects=sample_subjects[:5],
            )
            
            return sorted(filtered_items), stats
        except KeyboardInterrupt:
            interrupt_button_placeholder.empty()
            progress_bar.empty()
            status_text.empty()
            st.session_state.interrupt_scan = False
            st.session_state.scan_in_progress = False
            st.warning("⚠️ Analysis interrupted. Emails are already fetched. Click 'Continue Analysis' to process them.")
            raise
        finally:
            interrupt_button_placeholder.empty()
            progress_bar.empty()
            status_text.empty()
    
    # Function to perform the actual scan
    def perform_scan(cfg, skip_llm=False, use_fetched_emails=False):
        """Execute the email scan with progress tracking."""
        try:
            # Validate configuration before attempting connection
            if not cfg.email_address:
                st.error("Please provide your email address in the sidebar.")
                return
            
            # Check password (always using IMAP now)
            if not cfg.email_password:
                st.error("Please provide your email app password in the sidebar.")
                return
            
            # Reset interrupt flag
            st.session_state.interrupt_scan = False
            st.session_state.scan_in_progress = True
            
            # If we have pre-fetched emails, just process them
            if use_fetched_emails and st.session_state.fetched_emails:
                messages = st.session_state.fetched_emails
                deadlines, stats = process_fetched_emails(cfg, messages, skip_llm=skip_llm)
            else:
                # Two-phase approach: fetch first, then process
                agent = DeadlineAgent(cfg)
                
                # Phase 1: Fetch emails
                progress_bar = st.progress(0)
                status_text = st.empty()
                interrupt_button_placeholder = st.empty()
                
                status_text.text("Connecting to email server...")
                progress_bar.progress(0.05)
                
                # Show interrupt button during fetch
                with interrupt_button_placeholder.container():
                    if st.button("⏹️ Interrupt Connection", key="interrupt_fetch_btn", type="secondary"):
                        st.session_state.interrupt_scan = True
                        st.session_state.scan_in_progress = False
                        progress_bar.empty()
                        status_text.empty()
                        interrupt_button_placeholder.empty()
                        st.warning("⚠️ Connection interrupted. No emails were fetched.")
                        return
                
                try:
                    # Fetch emails
                    if st.session_state.interrupt_scan:
                        raise KeyboardInterrupt("Connection interrupted")
                    
                    messages = agent.fetch_emails_only()
                    st.session_state.fetched_emails = messages
                    emails_fetched = len(messages)
                    
                    if st.session_state.interrupt_scan:
                        raise KeyboardInterrupt("Connection interrupted")
                    
                    progress_bar.progress(0.1)
                    status_text.text(f"Fetched {emails_fetched} emails. Starting analysis...")
                    
                    # Clear interrupt button for fetch phase
                    interrupt_button_placeholder.empty()
                    
                    # Phase 2: Process emails
                    deadlines, stats = process_fetched_emails(cfg, messages, skip_llm=skip_llm)
                    
                except KeyboardInterrupt:
                    interrupt_button_placeholder.empty()
                    progress_bar.empty()
                    status_text.empty()
                    st.session_state.interrupt_scan = False
                    st.session_state.scan_in_progress = False
                    if st.session_state.fetched_emails:
                        st.warning("⚠️ Connection interrupted. However, emails were already fetched. Click 'Continue Analysis' below to process them.")
                    else:
                        st.warning("⚠️ Connection interrupted. No emails were fetched.")
                    return
                finally:
                    interrupt_button_placeholder.empty()
                    progress_bar.empty()
                    status_text.empty()
            
            # Process results (common for both paths)
            st.session_state.deadlines = deadlines
            # By default, exclude "general" category items from reminders
            selected_indices = set()
            for idx, item in enumerate(deadlines):
                category = getattr(item, 'category', 'general')
                if category != 'general':
                    selected_indices.add(idx)
            st.session_state.selected = selected_indices
            st.session_state.scan_stats = stats
            # Store last scan timestamp and email address
            st.session_state.last_scan_time = datetime.now()
            st.session_state.last_scan_email = cfg.email_address
            # Clear fetched emails after successful processing
            st.session_state.fetched_emails = None
            
            if len(deadlines) == 0:
                st.warning(f"⚠️ Found 0 deadlines after scanning {stats.emails_fetched} emails")
            else:
                st.success(f"Found {len(deadlines)} potential deadlines")
            
            # Always show stats if debug mode, or if no deadlines found
            if cfg.debug or len(deadlines) == 0:
                with st.expander("📊 Scan Statistics", expanded=cfg.debug or len(deadlines) == 0):
                    st.metric("Emails fetched", stats.emails_fetched)
                    st.metric("Emails processed", stats.emails_processed)
                    st.metric("Deadlines found", stats.deadlines_found)
                    st.metric("Unique senders", stats.unique_senders)
                    if stats.sample_subjects:
                        st.markdown("**Sample email subjects:**")
                        for subj in stats.sample_subjects:
                            st.text(f"  • {subj}")
                    if stats.emails_fetched == 0:
                        st.error("No emails were fetched. Check your email settings and date range.")
        except ValueError as e:
            # User-friendly error messages (like app password required)
            st.error(str(e))
            st.info("💡 **Tip:** Expand 'How to get an app password' in the sidebar for step-by-step instructions.")
        except FileNotFoundError as e:
            st.error(f"File not found: {e}. Please check your file paths in the sidebar.")
        except InsufficientFundsError as e:
            st.error("💳 **Insufficient Funds**")
            st.markdown(f"""
            {str(e)}
            
            **To add funds to your OpenAI account:**
            1. Go to [OpenAI Billing](https://platform.openai.com/account/billing)
            2. Add a payment method or top up your account
            3. Once funds are added, try scanning again
            
            You can also check your current usage and costs at [OpenAI Usage](https://platform.openai.com/usage)
            """)
        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__
            
            # Fallback check for insufficient funds (in case exception wasn't caught properly)
            if "insufficient" in error_msg.lower() and ("fund" in error_msg.lower() or "quota" in error_msg.lower() or "billing" in error_msg.lower()):
                st.error("💳 **Insufficient Funds**")
                st.markdown(f"""
                {error_msg}
                
                **To add funds to your OpenAI account:**
                1. Go to [OpenAI Billing](https://platform.openai.com/account/billing)
                2. Add a payment method or top up your account
                3. Once funds are added, try scanning again
                
                You can also check your current usage and costs at [OpenAI Usage](https://platform.openai.com/usage)
                """)
            elif "Application-specific password" in error_msg or "185833" in error_msg:
                st.error("❌ **App password required!** You're using your regular Gmail password. Please generate an app password - see instructions in the sidebar.")
            else:
                st.error(f"Error during scan: {error_msg}")
                with st.expander("Technical details"):
                    st.exception(e)
        finally:
            st.session_state.scan_in_progress = False
    
    # Initialize scan trigger state
    if "trigger_scan" not in st.session_state:
        st.session_state.trigger_scan = False
    
    col1, col2 = st.columns(2)
    with col1:
        # Check if we're in confirmation mode
        if "show_llm_confirmation" not in st.session_state:
            st.session_state.show_llm_confirmation = False
        
        # Show confirmation dialog if waiting for LLM confirmation
        if st.session_state.waiting_llm_confirmation and cfg.use_llm_extraction and st.session_state.fetched_email_count is not None:
            # Calculate cost based on actual email count
            actual_emails = st.session_state.fetched_email_count
            cost_per_email = 0.0003 if cfg.llm_model == "gpt-4o-mini" else (0.003 if cfg.llm_model == "gpt-4o" else 0.01)
            estimated_cost = actual_emails * cost_per_email
            
            with st.container(border=True):
                st.warning("⚠️ **LLM Extraction Cost Estimate**")
                st.markdown(f"""
                **Emails found:** {actual_emails} emails
                
                **Estimated cost:** ~${estimated_cost:.2f} - ${estimated_cost * 1.5:.2f}
                
                - Model: {cfg.llm_model}
                - Cost varies based on email length
                - You'll be charged by OpenAI based on actual usage
                - [Check usage & costs](https://platform.openai.com/usage) to see current spending
                """)
                dont_remind = st.checkbox("Don't remind me again", key="dont_remind_llm")
                col_confirm, col_cancel = st.columns(2)
                with col_confirm:
                    if st.button("Continue with LLM extraction", type="primary", key="confirm_llm_scan"):
                        if dont_remind:
                            st.session_state.skip_scan_confirmation = True
                        st.session_state.waiting_llm_confirmation = False
                        st.session_state.trigger_scan = True
                        st.rerun()
                with col_cancel:
                    if st.button("Skip LLM, use regex only", key="skip_llm_scan"):
                        st.session_state.waiting_llm_confirmation = False
                        st.session_state.trigger_scan = True
                        st.session_state.skip_llm_for_scan = True
                        st.rerun()
        elif st.button("Authenticate & Scan", type="primary", help="Connect to your email and scan for deadlines. This may take a few moments depending on the number of emails."):
            # If LLM is enabled, first fetch emails to show cost
            if cfg.use_llm_extraction and not st.session_state.skip_scan_confirmation:
                try:
                    if fetch_emails_for_cost(cfg):
                        st.session_state.waiting_llm_confirmation = True
                        st.rerun()
                except Exception as e:
                    st.error(f"Error fetching emails: {str(e)}")
            else:
                # Proceed directly with scan (LLM disabled or confirmation skipped)
                perform_scan(cfg, skip_llm=(getattr(st.session_state, 'skip_llm_for_scan', False)))
    
    # Trigger scan after confirmation dialog is dismissed
    if st.session_state.trigger_scan:
        st.session_state.trigger_scan = False
        skip_llm = getattr(st.session_state, 'skip_llm_for_scan', False)
        if skip_llm:
            st.session_state.skip_llm_for_scan = False
        perform_scan(cfg, skip_llm=skip_llm)
    
    # Display last scan timestamp if available
    if "last_scan_time" in st.session_state and st.session_state.last_scan_time:
        last_scan = st.session_state.last_scan_time
        time_ago = datetime.now() - last_scan
        if time_ago.total_seconds() < 60:
            time_str = f"{int(time_ago.total_seconds())} seconds ago"
        elif time_ago.total_seconds() < 3600:
            time_str = f"{int(time_ago.total_seconds() / 60)} minutes ago"
        else:
            time_str = f"{int(time_ago.total_seconds() / 3600)} hours ago"
        
        # Include email address if available
        email_info = ""
        if "last_scan_email" in st.session_state and st.session_state.last_scan_email:
            email_info = f" ({st.session_state.last_scan_email})"
        
        st.caption(f"🕐 Last scanned: {last_scan.strftime('%Y-%m-%d %H:%M:%S')} ({time_str}){email_info}")
    
    # Show "Continue Analysis" button if emails are fetched but scan was interrupted
    if st.session_state.fetched_emails and not st.session_state.scan_in_progress and not st.session_state.deadlines:
        st.info(f"📧 **{len(st.session_state.fetched_emails)} emails are ready for analysis.** Click below to continue processing them.")
        if st.button("▶️ Continue Analysis", type="primary", help="Process the already-fetched emails to find deadlines"):
            skip_llm = getattr(st.session_state, 'skip_llm_for_scan', False)
            perform_scan(cfg, skip_llm=skip_llm, use_fetched_emails=True)
    
    with col2:
        if st.button("Clear Results", help="Clear all scanned deadlines and reset the view"):
            st.session_state.deadlines = []
            st.session_state.selected = set()
            st.session_state.scan_stats = None

    deadlines = st.session_state.deadlines
    if deadlines:
        st.subheader("Review detected deadlines")
        
        # Show global selection count
        total_deadlines = len(deadlines)
        selected_count = len(st.session_state.selected)
        st.caption(f"Selected: {selected_count} of {total_deadlines} deadlines")
        
        # Category color mapping
        category_colors = {
            "subscription": "🔵",
            "trial": "🟡",
            "travel": "✈️",
            "billing": "💰",
            "refund": "💸",
            "general": "⚪"
        }
        
        # Group deadlines by category
        deadlines_by_category = {}
        for idx, item in enumerate(deadlines):
            category = getattr(item, 'category', 'general')
            if category not in deadlines_by_category:
                deadlines_by_category[category] = []
            deadlines_by_category[category].append((idx, item))
        
        # Sort categories: subscription, trial, travel, billing, refund, then general
        category_order = ["subscription", "trial", "travel", "billing", "refund", "general"]
        sorted_categories = sorted(
            deadlines_by_category.keys(),
            key=lambda c: (category_order.index(c) if c in category_order else 999, c)
        )
        
        # Debug: Show category breakdown (can be removed later)
        if cfg.debug:
            st.caption(f"📊 Categories found: {sorted_categories} | Total deadlines: {len(deadlines)}")
        
        def render_deadline_item(item, actual_idx, show_checkbox=False):
            """Render a single deadline item"""
            item_category = getattr(item, 'category', 'general')
            # Checkbox is now rendered outside this function, but we keep this for backward compatibility
            if show_checkbox:
                is_selected = actual_idx in st.session_state.selected
                selected = st.checkbox(
                    "Include", 
                    value=is_selected, 
                    key=f"sel_{actual_idx}",
                    help="Check to include this deadline in calendar reminders"
                )
                if selected:
                    st.session_state.selected.add(actual_idx)
                else:
                    st.session_state.selected.discard(actual_idx)
                if item_category == "general":
                    st.caption("⚠️ General category - excluded by default")
            col1, col2 = st.columns(2)
            with col1:
                st.text(f"Category: **{item_category.title()}**")
                st.text(f"Source: {item.source}")
                if getattr(item, 'email_date', None):
                    st.text(f"📧 Email received: {item.email_date.strftime('%Y-%m-%d %H:%M')}")
            with col2:
                st.text(f"Confidence: {item.confidence:.2f}")
                st.text(f"⏰ Deadline: {item.deadline_at.strftime('%Y-%m-%d %H:%M')}")
            
            # Show email excerpt or summary
            email_excerpt = getattr(item, 'email_excerpt', None)
            email_summary = getattr(item, 'email_summary', None)
            
            # Always try to show some context - prioritize summary, then excerpt, then context
            if email_summary:
                st.markdown("**📝 LLM Summary:**")
                st.info(email_summary)
                if email_excerpt:
                    show_excerpt = st.checkbox("📄 Show original email excerpt", key=f"show_excerpt_{actual_idx}", value=False)
                    if show_excerpt:
                        st.text_area("", value=email_excerpt, height=100, disabled=True, key=f"excerpt_{actual_idx}", label_visibility="collapsed")
            elif email_excerpt and email_excerpt.strip():
                st.markdown("**📄 Email Excerpt:**")
                st.text_area(
                    "", 
                    value=email_excerpt, 
                    height=120, 
                    disabled=True,
                    key=f"excerpt_{actual_idx}",
                    label_visibility="collapsed"
                )
            elif item.context and item.context.strip():
                st.markdown("**📄 Context (from matched pattern):**")
                st.text_area(
                    "",
                    value=item.context,
                    height=80,
                    disabled=True,
                    key=f"context_{actual_idx}",
                    label_visibility="collapsed"
                )
            else:
                st.caption("ℹ️ No excerpt available. Click 'Clear Results' and rescan to get email excerpts.")
            wrong = st.toggle("This is incorrect", key=f"wrong_{actual_idx}")
            if wrong:
                reason = st.text_input("Why is it incorrect? (optional)", key=f"reason_{actual_idx}")
                if st.button("Submit feedback", key=f"fb_{actual_idx}"):
                    store_feedback(item, reason or "")
                    st.success("Thanks for the feedback!")
        
        # Create tabs for each category - always use tabs when there are results
        if sorted_categories:
            # Create tab labels with category emoji and count
            tab_labels = [f"{category_colors.get(cat, '⚪')} {cat.title()} ({len(deadlines_by_category[cat])})" for cat in sorted_categories]
            tabs = st.tabs(tab_labels)
            
            # Render content in each tab
            for tab, category in zip(tabs, sorted_categories):
                with tab:
                    category_deadlines = deadlines_by_category[category]
                    if not category_deadlines:
                        st.info("No deadlines in this category")
                    else:
                        # Per-category Select All / Deselect All toggle
                        category_indices = [idx for idx, _ in category_deadlines]
                        category_selected = [idx for idx in category_indices if idx in st.session_state.selected]
                        category_selected_count = len(category_selected)
                        all_category_selected = category_selected_count == len(category_indices)
                        
                        col_select_all, col_info = st.columns([1, 4])
                        with col_select_all:
                            if all_category_selected:
                                if st.button("Deselect All", key=f"deselect_all_{category}_btn", help=f"Uncheck all {category} deadlines"):
                                    for idx in category_indices:
                                        st.session_state.selected.discard(idx)
                                    st.rerun()
                            else:
                                if st.button("Select All", key=f"select_all_{category}_btn", help=f"Check all {category} deadlines"):
                                    for idx in category_indices:
                                        st.session_state.selected.add(idx)
                                    st.rerun()
                        with col_info:
                            st.caption(f"Selected: {category_selected_count} of {len(category_indices)} in this category")
                        
                        for actual_idx, item in category_deadlines:
                            item_category = getattr(item, 'category', 'general')
                            category_emoji = category_colors.get(item_category, "⚪")
                            
                            # Check selection state first
                            is_selected = actual_idx in st.session_state.selected
                            
                            # Render checkbox outside the expander for easy access
                            col_checkbox, col_expander = st.columns([1, 20])
                            with col_checkbox:
                                selected = st.checkbox(
                                    "",
                                    value=is_selected,
                                    key=f"sel_{actual_idx}",
                                    help="Include this deadline in calendar reminders",
                                    label_visibility="collapsed"
                                )
                                if selected:
                                    st.session_state.selected.add(actual_idx)
                                else:
                                    st.session_state.selected.discard(actual_idx)
                            
                            with col_expander:
                                # Show checkbox status in expander label
                                checkbox_indicator = "☑️" if (actual_idx in st.session_state.selected) else "☐"
                                with st.expander(f"{checkbox_indicator} {item.deadline_at.strftime('%Y-%m-%d %H:%M')} · {category_emoji} {item.title}"):
                                    render_deadline_item(item, actual_idx)
        else:
            # Fallback: no categories found (shouldn't happen, but handle gracefully)
            st.warning("No categories found in deadlines")
            for idx, item in enumerate(deadlines):
                category_emoji = "⚪"
                
                # Check selection state first
                is_selected = idx in st.session_state.selected
                
                # Render checkbox outside the expander for easy access
                col_checkbox, col_expander = st.columns([1, 20])
                with col_checkbox:
                    selected = st.checkbox(
                        "",
                        value=is_selected,
                        key=f"sel_{idx}",
                        help="Include this deadline in calendar reminders",
                        label_visibility="collapsed"
                    )
                    if selected:
                        st.session_state.selected.add(idx)
                    else:
                        st.session_state.selected.discard(idx)
                
                with col_expander:
                    # Show checkbox status in expander label
                    checkbox_indicator = "☑️" if (idx in st.session_state.selected) else "☐"
                    with st.expander(f"{checkbox_indicator} {item.deadline_at.strftime('%Y-%m-%d %H:%M')} · {category_emoji} {item.title}"):
                        render_deadline_item(item, idx)

        st.divider()
        st.subheader("Create calendar reminders for selected")
        remind_minutes_before = st.number_input(
            "Reminder: minutes before", 
            min_value=0, 
            max_value=1440, 
            value=60,
            help="Set how many minutes before the deadline you want to be reminded. Default is 60 minutes (1 hour)."
        )
        if st.button("Create Reminders", help="Generate a .ics calendar file with reminders for all selected deadlines. You can import this file into Google Calendar, Outlook, Apple Calendar, etc."):
            svc = CalendarService()
            selected_requests: List[CalendarEventRequest] = []
            for idx in sorted(st.session_state.selected):
                item = deadlines[idx]
                
                # Build a comprehensive description with all available information
                # Note: Emojis will be removed by calendar.py for .ics compatibility
                description_parts = []
                
                # Category and confidence
                description_parts.append(f"Category: {item.category.title()}")
                description_parts.append(f"Confidence: {item.confidence:.0%}")
                
                # Source information
                description_parts.append(f"Source: {item.source}")
                
                # Email date if available
                if item.email_date:
                    description_parts.append(f"Email received: {item.email_date.strftime('%Y-%m-%d %H:%M')}")
                
                # LLM summary (most useful, if available)
                if item.email_summary:
                    description_parts.append(f"Summary: {item.email_summary}")
                
                # Email excerpt (if no summary available)
                elif item.email_excerpt:
                    excerpt = item.email_excerpt[:300].replace('\n', ' ').strip()  # Limit and clean
                    description_parts.append(f"Email excerpt: {excerpt}")
                
                # Context (fallback)
                elif item.context:
                    context = item.context[:300].replace('\n', ' ').strip()  # Limit and clean
                    description_parts.append(f"Context: {context}")
                
                # Link if available
                if item.link:
                    description_parts.append(f"Link: {item.link}")
                
                # Add footer
                description_parts.append("Generated by Deadline Agent")
                
                # Join with newlines (will be escaped to \n in .ics format)
                description = "\n".join(description_parts)
                
                selected_requests.append(
                    CalendarEventRequest(
                        title=item.title,
                        starts_at=item.deadline_at,
                        duration_minutes=30,
                        description=description,
                    )
                )
            if selected_requests:
                ics = svc.generate_ics(selected_requests, reminder_minutes_before=int(remind_minutes_before))
                st.session_state.generated_ics = ics
                st.success(f"Prepared {len(selected_requests)} reminder(s). Download below.")

        # Show download button - disabled until reminders are created
        if "generated_ics" in st.session_state and st.session_state.generated_ics:
            st.download_button(
                label="Download .ics",
                data=st.session_state.generated_ics.encode("utf-8"),
                file_name="deadlines.ics",
                mime="text/calendar",
                help="Download the calendar file and import it into your calendar app (Google Calendar, Outlook, Apple Calendar, etc.)"
            )
        else:
            # Show disabled button when no .ics file is ready
            st.button(
                label="Download .ics",
                disabled=True,
                help="Click 'Create Reminders' above to generate the calendar file first"
            )

    # Page footer
    st.divider()
    footer_col1, footer_col2, footer_col3 = st.columns([2, 1, 2])
    with footer_col1:
        st.markdown("")
    with footer_col2:
        st.markdown(
            f"<div style='text-align: center; color: #666; font-size: 0.85em; padding: 10px 0;'>"
            f"Deadline Agent v{VERSION} | "
            f"About Us: <a href='mailto:smartretireai@gmail.com' style='color: #666; text-decoration: none;'>smartretireai@gmail.com</a>"
            f"</div>",
            unsafe_allow_html=True
        )
    with footer_col3:
        st.markdown("")

    # Feedback section
    st.sidebar.divider()
    with st.sidebar.expander("📊 Feedback Analytics", expanded=False):
        learner = FeedbackLearner(FEEDBACK_FILE)
        stats = learner.get_stats()
        
        if stats.total_feedback > 0:
            st.write(f"**{stats.total_feedback} feedback entries**")
            
            # Top problematic senders
            if stats.false_positives_by_sender:
                st.markdown("**Top flagged senders:**")
                sorted_senders = sorted(stats.false_positives_by_sender.items(), key=lambda x: x[1], reverse=True)[:5]
                for sender, count in sorted_senders:
                    sender_short = sender[:30] + "..." if len(sender) > 30 else sender
                    st.caption(f"  • {sender_short}: {count} time{'s' if count > 1 else ''}")
            
            # Most common reasons
            if stats.most_common_reasons:
                st.markdown("**Common issues:**")
                sorted_reasons = sorted(stats.most_common_reasons.items(), key=lambda x: x[1], reverse=True)[:3]
                for reason, count in sorted_reasons:
                    reason_short = reason[:40] + "..." if len(reason) > 40 else reason
                    st.caption(f"  • {reason_short}: {count}x")
            
            st.caption("💡 System learns from feedback to filter similar false positives")
        else:
            st.write("No feedback collected yet")
            st.caption("Submit feedback on incorrect deadlines to help improve accuracy")

    # Version footer
    st.sidebar.divider()
    st.sidebar.caption(f"Deadline Agent v{VERSION}")


if __name__ == "__main__":
    main()

