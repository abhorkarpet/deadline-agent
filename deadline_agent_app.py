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
VERSION = "3.0.0"


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
    st.title("Deadline Agent")
    st.caption("Authenticate, scan inbox for deadlines, review results, and create reminders")
    
    # Browser recommendation
    st.info("💡 **Best experience:** Use Chrome browser on Desktop for optimal performance")

    # Render sidebar/config
    cfg = get_config_from_ui()

    # Optional Welcome / Onboarding
    if "suppress_welcome" not in st.session_state:
        st.session_state.suppress_welcome = False
    if "welcomed" not in st.session_state:
        st.session_state.welcomed = False

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
        dont_show = st.checkbox("Don't show again", value=st.session_state.suppress_welcome, key="suppress_welcome_checkbox")
        if st.button("I understand, continue →", key="welcome_continue"):
            if dont_show:
                st.session_state.suppress_welcome = True
            else:
                st.session_state.suppress_welcome = False
            st.session_state.welcomed = True
            st.rerun()

    # Show welcome only if not suppressed and not yet welcomed
    if not st.session_state.suppress_welcome and not st.session_state.welcomed:
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
    
    # Function to perform the actual scan
    def perform_scan(cfg, skip_llm=False):
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
            
            # Create agent (always using IMAP now)
            agent = DeadlineAgent(cfg)
            
            # Progress tracking
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            def update_progress(message: str, progress: float):
                progress_bar.progress(progress)
                status_text.text(message)
            
            try:
                deadlines, stats = agent.collect_deadlines(progress_callback=update_progress, skip_llm=skip_llm)
            finally:
                # Clear progress indicators
                progress_bar.empty()
                status_text.empty()
            
            st.session_state.deadlines = deadlines
            # By default, exclude "general" category items from reminders
            selected_indices = set()
            for idx, item in enumerate(deadlines):
                category = getattr(item, 'category', 'general')
                if category != 'general':
                    selected_indices.add(idx)
            st.session_state.selected = selected_indices
            st.session_state.scan_stats = stats
            
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
        elif st.button("Authenticate & Scan", type="primary"):
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
    with col2:
        if st.button("Clear Results"):
            st.session_state.deadlines = []
            st.session_state.selected = set()
            st.session_state.scan_stats = None

    deadlines = st.session_state.deadlines
    if deadlines:
        st.subheader("Review detected deadlines")
        
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
        
        def render_deadline_item(item, actual_idx):
            """Render a single deadline item"""
            item_category = getattr(item, 'category', 'general')
            is_selected = actual_idx in st.session_state.selected
            # Make "Include" checkbox more prominent
            col_include, col_info = st.columns([1, 4])
            with col_include:
                selected = st.checkbox(
                    "Include", 
                    value=is_selected, 
                    key=f"sel_{actual_idx}",
                    help="Check to include this deadline in calendar reminders"
                )
            with col_info:
                if item_category == "general":
                    st.caption("⚠️ General category - excluded by default")
            if selected:
                st.session_state.selected.add(actual_idx)
            else:
                st.session_state.selected.discard(actual_idx)
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
                        for actual_idx, item in category_deadlines:
                            item_category = getattr(item, 'category', 'general')
                            category_emoji = category_colors.get(item_category, "⚪")
                            with st.expander(f"{item.deadline_at.strftime('%Y-%m-%d %H:%M')} · {category_emoji} {item.title}"):
                                render_deadline_item(item, actual_idx)
        else:
            # Fallback: no categories found (shouldn't happen, but handle gracefully)
            st.warning("No categories found in deadlines")
            for idx, item in enumerate(deadlines):
                category_emoji = "⚪"
                with st.expander(f"{item.deadline_at.strftime('%Y-%m-%d %H:%M')} · {category_emoji} {item.title}"):
                    render_deadline_item(item, idx)

        st.divider()
        st.subheader("Create calendar reminders for selected")
        remind_minutes_before = st.number_input("Reminder: minutes before", min_value=0, max_value=1440, value=60)
        if st.button("Create Reminders"):
            svc = CalendarService()
            selected_requests: List[CalendarEventRequest] = []
            for idx in sorted(st.session_state.selected):
                item = deadlines[idx]
                selected_requests.append(
                    CalendarEventRequest(
                        title=item.title,
                        starts_at=item.deadline_at,
                        duration_minutes=30,
                        description=item.context or f"Source: {item.source}",
                    )
                )
            if selected_requests:
                ics = svc.generate_ics(selected_requests, reminder_minutes_before=int(remind_minutes_before))
                st.session_state.generated_ics = ics
                st.success(f"Prepared {len(selected_requests)} reminder(s). Download below.")

        if "generated_ics" in st.session_state and st.session_state.generated_ics:
            st.download_button(
                label="Download .ics",
                data=st.session_state.generated_ics.encode("utf-8"),
                file_name="deadlines.ics",
                mime="text/calendar",
            )

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


