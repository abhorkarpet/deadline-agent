from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class EmailMessageData:
    uid: str
    subject: str
    sender: str
    date: datetime
    text: str
    html: Optional[str]
    source_mailbox: str


@dataclass(order=True)
class DeadlineItem:
    deadline_at: datetime
    title: str
    source: str
    link: Optional[str] = None
    confidence: float = 0.0
    context: Optional[str] = None
    category: str = "general"  # general, subscription, travel, trial, billing, refund
    email_date: Optional[datetime] = None  # Date when the email was received
    email_excerpt: Optional[str] = None  # Relevant excerpt from the email
    email_summary: Optional[str] = None  # LLM-generated summary (if available)



