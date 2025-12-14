from dataclasses import dataclass
from typing import List, Tuple, Optional

from google.oauth2.credentials import Credentials

from .config import AgentConfig
from .email_client import EmailClient
from .gmail_api_client import GmailAPIClient
from .models import DeadlineItem, EmailMessageData
from .parsers import DeadlineExtractor
from .feedback_learner import FeedbackLearner

try:
    from .llm_extractor import LLMExtractor
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    LLMExtractor = None


@dataclass
class ScanStats:
    emails_fetched: int
    emails_processed: int
    deadlines_found: int
    unique_senders: int
    sample_subjects: List[str]


class DeadlineAgent:
    def __init__(self, config: AgentConfig, oauth_credentials: Optional[Credentials] = None):
        self.config = config
        self.client = self._select_client(oauth_credentials)
        self.regex_extractor = DeadlineExtractor(reference_now=None)
        self.feedback_learner = FeedbackLearner()
        self.llm_extractor = None
        if config.use_llm_extraction:
            if not LLM_AVAILABLE:
                if self.config.debug:
                    print("Warning: openai package not installed. Install with: pip install openai")
            elif not config.llm_api_key:
                if self.config.debug:
                    print("Warning: LLM extraction enabled but no API key provided")
            else:
                try:
                    self.llm_extractor = LLMExtractor(api_key=config.llm_api_key, model=config.llm_model)
                except Exception as e:
                    if self.config.debug:
                        print(f"Warning: LLM extractor initialization failed: {e}")
                    self.llm_extractor = None

    def _select_client(self, oauth_credentials: Optional[Credentials] = None):
        """
        Select appropriate email client based on auth_method and provider.
        Returns EmailClient or GmailAPIClient.
        """
        # Determine if Gmail
        is_gmail = self.config.is_gmail()
        
        # Check auth_method (prefer new method, fallback to use_gmail_api for backward compat)
        use_oauth = False
        if self.config.auth_method == "oauth":
            use_oauth = True
        elif self.config.use_gmail_api:  # Backward compatibility
            use_oauth = True
        
        # Use Gmail OAuth if:
        # 1. Gmail address AND
        # 2. OAuth method selected AND
        # 3. (OAuth credentials provided OR client_id/secret configured)
        if is_gmail and use_oauth:
            if oauth_credentials:
                # Use provided credentials (from Streamlit session state)
                return GmailAPIClient(self.config, credentials=oauth_credentials)
            elif self.config.oauth_client_id and self.config.oauth_client_secret:
                # OAuth configured, will authorize on first use
                return GmailAPIClient(self.config)
            elif self.config.oauth_client_secret_path:
                # Legacy: using client_secret.json file
                return GmailAPIClient(self.config)
            else:
                # OAuth selected but not configured, fallback to IMAP
                if self.config.debug:
                    print("Warning: OAuth selected but credentials not found. Falling back to IMAP.")
                return EmailClient(self.config)
        else:
            # Use IMAP (for non-Gmail or if IMAP explicitly selected)
            return EmailClient(self.config)

    def fetch_emails_only(self) -> List[EmailMessageData]:
        """Fetch emails without processing. Returns list of EmailMessageData."""
        return self.client.fetch_recent_messages()
    
    def collect_deadlines(self, progress_callback=None, skip_llm=False) -> Tuple[List[DeadlineItem], ScanStats]:
        if progress_callback:
            progress_callback("Connecting to email server...", 0.0)
        
        messages = self.client.fetch_recent_messages()
        emails_fetched = len(messages)
        
        if progress_callback:
            progress_callback(f"Fetched {emails_fetched} emails. Processing...", 0.1)
        
        all_items: List[DeadlineItem] = []
        senders = set()
        sample_subjects = []
        
        total = len(messages)
        batch_size = 100
        
        # Process emails in batches of 100
        num_batches = (total + batch_size - 1) // batch_size  # Ceiling division
        
        for batch_idx in range(num_batches):
            start_idx = batch_idx * batch_size
            end_idx = min(start_idx + batch_size, total)
            batch = messages[start_idx:end_idx]
            
            # Update progress for batch
            if progress_callback and total > 0:
                progress_pct = 0.1 + (start_idx / total) * 0.8  # 10% to 90% for processing
                progress_callback(f"Processing batch {batch_idx + 1}/{num_batches} (emails {start_idx + 1}-{end_idx}/{total})...", progress_pct)
            
            # Process each email in the batch
            for msg in batch:
                senders.add(msg.sender)
                if len(sample_subjects) < 5:
                    sample_subjects.append(msg.subject[:60])
                
                # Try regex first (fast, free)
                regex_items = self.regex_extractor.extract_from_message(msg)
                all_items.extend(regex_items)
                
                # Try LLM if enabled (slower, costs money, but catches more cases)
                if self.llm_extractor and not skip_llm:
                    try:
                        llm_items = self.llm_extractor.extract_from_message(msg)
                        all_items.extend(llm_items)
                    except Exception as e:
                        # Re-raise InsufficientFundsError to be handled by UI
                        from .llm_extractor import InsufficientFundsError
                        if isinstance(e, InsufficientFundsError):
                            raise
                        if self.config.debug:
                            print(f"LLM extraction error for {msg.subject}: {e}")
        
        if progress_callback:
            progress_callback(f"Found {len(all_items)} potential deadlines. Applying filters...", 0.9)
        
        # Apply feedback-based filtering and confidence adjustment
        filtered_items = self.feedback_learner.apply_feedback_learning(all_items)
        filtered_count = len(all_items) - len(filtered_items)
        
        if self.config.debug and filtered_count > 0:
            print(f"Feedback learning filtered out {filtered_count} items")
        
        if progress_callback:
            progress_callback(f"Complete! Found {len(filtered_items)} deadlines.", 1.0)
        
        stats = ScanStats(
            emails_fetched=emails_fetched,
            emails_processed=len(messages),
            deadlines_found=len(filtered_items),
            unique_senders=len(senders),
            sample_subjects=sample_subjects[:5],
        )
        
        return sorted(filtered_items), stats



