import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional, Tuple

import dateparser
from bs4 import BeautifulSoup

from .models import DeadlineItem, EmailMessageData


# Pattern and category pairs
DEADLINE_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"free trial ends on\s*([^.\n]+)", re.IGNORECASE), "trial"),
    (re.compile(r"trial period ends\s*(on|by)?\s*([^.\n]+)", re.IGNORECASE), "trial"),
    (re.compile(r"renew(s|al) on\s*([^.\n]+)", re.IGNORECASE), "subscription"),
    (re.compile(r"subscription renew(s|al)\s*(on|by)?\s*([^.\n]+)", re.IGNORECASE), "subscription"),
    (re.compile(r"next billing date\s*(is|:)\s*([^.\n]+)", re.IGNORECASE), "billing"),
    (re.compile(r"billing date\s*(is|:)\s*([^.\n]+)", re.IGNORECASE), "billing"),
    (re.compile(r"cancel by\s*([^.\n]+)", re.IGNORECASE), "general"),
    (re.compile(r"cancellation deadline\s*(is|:)\s*([^.\n]+)", re.IGNORECASE), "general"),
    (re.compile(r"fully refundable until\s*([^.\n]+)", re.IGNORECASE), "refund"),
    (re.compile(r"refund deadline\s*(is|:)\s*([^.\n]+)", re.IGNORECASE), "refund"),
    (re.compile(r"(hotel|flight|booking|reservation).*cancel.*(by|until|before)\s*([^.\n]+)", re.IGNORECASE), "travel"),
    (re.compile(r"cancel.*(hotel|flight|booking|reservation).*(by|until|before)\s*([^.\n]+)", re.IGNORECASE), "travel"),
]


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.extract()
    text = soup.get_text(" ", strip=True)
    return text


def _parse_date(s: str, ref: datetime) -> Optional[datetime]:
    return dateparser.parse(
        s,
        settings={
            "RELATIVE_BASE": ref,
            "RETURN_AS_TIMEZONE_AWARE": False,
            "PREFER_DATES_FROM": "future",
        },
    )


class DeadlineExtractor:
    """Regex-based deadline extractor (fast, no API cost)."""
    
    def __init__(self, reference_now: Optional[datetime] = None):
        self.reference_now = reference_now or datetime.utcnow()

    def extract_from_message(self, msg: EmailMessageData) -> List[DeadlineItem]:
        corpus = msg.text or ""
        if msg.html:
            corpus = corpus + "\n" + _html_to_text(msg.html)

        candidates: List[DeadlineItem] = []
        for pattern, category in DEADLINE_PATTERNS:
            for match in pattern.finditer(corpus):
                groups = [g for g in match.groups() if g]
                if not groups:
                    continue
                date_str = groups[-1]
                parsed = _parse_date(date_str, msg.date or self.reference_now)
                if not parsed:
                    continue
                title = msg.subject or "Deadline"
                context_window = corpus[max(0, match.start() - 80) : match.end() + 80]
                # Filter out shopping offers by checking context
                context_lower = context_window.lower()
                if any(term in context_lower for term in ["sale", "discount", "off", "promo", "limited time", "deal expires"]):
                    # Skip if it looks like a shopping offer
                    if "subscription" not in context_lower and "trial" not in context_lower and "cancel" not in context_lower:
                        continue
                
                # Extract a better excerpt - get sentences around the match
                start_idx = max(0, match.start() - 250)
                end_idx = min(len(corpus), match.end() + 250)
                excerpt = corpus[start_idx:end_idx].strip()
                
                # Try to find sentence boundaries for cleaner excerpt
                if excerpt:
                    # Find last sentence start before match
                    sentence_start = max(0, excerpt.rfind('. ', 0, 250))
                    if sentence_start > 50:  # Only use if we found a sentence boundary
                        excerpt = excerpt[sentence_start:].strip()
                    
                    # Find first sentence end after match
                    sentence_end = excerpt.find('. ', 200)
                    if sentence_end > 200:
                        excerpt = excerpt[:sentence_end + 1].strip()
                    
                    # Clean up excerpt - remove extra whitespace
                    excerpt = " ".join(excerpt.split())
                    # Limit to 600 chars but ensure we have meaningful content
                    if len(excerpt) > 600:
                        excerpt = excerpt[:597] + "..."
                else:
                    # Fallback: use first 400 chars of email if excerpt extraction failed
                    excerpt = corpus[:400].strip()
                    excerpt = " ".join(excerpt.split())[:400]
                
                candidates.append(
                    DeadlineItem(
                        deadline_at=parsed,
                        title=title,
                        source=f"email:{msg.sender}",
                        link=None,
                        confidence=0.6,
                        context=context_window,
                        category=category,
                        email_date=msg.date,
                        email_excerpt=excerpt if excerpt else None,
                    )
                )

        # Remove duplicates by (date,title,source)
        unique: dict[Tuple[str, str, str], DeadlineItem] = {}
        for item in candidates:
            key = (item.deadline_at.isoformat(), item.title, item.source)
            if key not in unique or unique[key].confidence < item.confidence:
                unique[key] = item
        return sorted(unique.values())



