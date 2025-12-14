from dataclasses import dataclass
from typing import List, Tuple

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
    def __init__(self, config: AgentConfig):
        self.config = config
        self.client = GmailAPIClient(config) if config.use_gmail_api else EmailClient(config)
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
        for idx, msg in enumerate(messages):
            # Update progress
            if progress_callback and total > 0:
                progress_pct = 0.1 + (idx / total) * 0.8  # 10% to 90% for processing
                progress_callback(f"Processing email {idx + 1}/{total}...", progress_pct)
            
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



