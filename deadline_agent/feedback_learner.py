import json
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from .models import DeadlineItem


@dataclass
class FeedbackStats:
    total_feedback: int
    false_positives_by_sender: Dict[str, int]
    false_positives_by_keyword: Dict[str, int]
    most_common_reasons: Dict[str, int]


class FeedbackLearner:
    """Learns from user feedback to improve deadline extraction."""
    
    def __init__(self, feedback_file: str = "deadline_agent_feedback.jsonl"):
        self.feedback_file = feedback_file
        self._cache: Optional[FeedbackStats] = None
    
    def _load_feedback(self) -> List[dict]:
        """Load all feedback entries from file."""
        if not os.path.exists(self.feedback_file):
            return []
        
        feedback = []
        try:
            with open(self.feedback_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            feedback.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except Exception:
            pass
        
        return feedback
    
    def get_stats(self) -> FeedbackStats:
        """Calculate feedback statistics."""
        if self._cache is not None:
            return self._cache
        
        feedback = self._load_feedback()
        
        sender_counts = defaultdict(int)
        keyword_counts = defaultdict(int)
        reason_counts = defaultdict(int)
        
        for entry in feedback:
            # Count by sender
            source = entry.get("source", "")
            if "email:" in source:
                sender = source.split("email:")[-1].strip()
                sender_counts[sender] += 1
            
            # Extract keywords from title and reason
            title = entry.get("title", "").lower()
            reason = entry.get("reason", "").lower()
            combined = f"{title} {reason}"
            
            # Count common problematic keywords
            keywords = ["promotional", "marketing", "sale", "discount", "offer", "deal", "promo"]
            for keyword in keywords:
                if keyword in combined:
                    keyword_counts[keyword] += 1
            
            # Count reasons
            if reason:
                reason_counts[reason[:100]] += 1  # Truncate long reasons
        
        stats = FeedbackStats(
            total_feedback=len(feedback),
            false_positives_by_sender=dict(sender_counts),
            false_positives_by_keyword=dict(keyword_counts),
            most_common_reasons=dict(reason_counts),
        )
        
        self._cache = stats
        return stats
    
    def is_blacklisted_sender(self, sender: str, threshold: int = 2) -> bool:
        """Check if sender is blacklisted based on feedback."""
        stats = self.get_stats()
        count = stats.false_positives_by_sender.get(sender, 0)
        return count >= threshold
    
    def calculate_confidence_penalty(self, item: DeadlineItem) -> float:
        """Reduce confidence based on feedback patterns."""
        stats = self.get_stats()
        penalty = 0.0
        
        # Check sender blacklist
        source = item.source
        if "email:" in source:
            sender = source.split("email:")[-1].strip()
            sender_count = stats.false_positives_by_sender.get(sender, 0)
            if sender_count > 0:
                # Reduce confidence by 0.1 per feedback for this sender (max 0.5 reduction)
                penalty += min(sender_count * 0.1, 0.5)
        
        # Check for problematic keywords in title
        title_lower = item.title.lower()
        problematic_keywords = ["promotional", "marketing", "sale", "discount", "offer"]
        for keyword in problematic_keywords:
            if keyword in title_lower:
                keyword_count = stats.false_positives_by_keyword.get(keyword, 0)
                if keyword_count > 0:
                    penalty += 0.15
        
        return penalty
    
    def should_filter_item(self, item: DeadlineItem, min_confidence: float = 0.3) -> bool:
        """Determine if item should be filtered based on feedback."""
        # Check sender blacklist
        source = item.source
        if "email:" in source:
            sender = source.split("email:")[-1].strip()
            if self.is_blacklisted_sender(sender, threshold=3):
                return True
        
        # Apply confidence penalty
        original_confidence = item.confidence
        penalty = self.calculate_confidence_penalty(item)
        adjusted_confidence = original_confidence - penalty
        
        # Filter if confidence drops below threshold
        if adjusted_confidence < min_confidence:
            return True
        
        return False
    
    def apply_feedback_learning(self, items: List[DeadlineItem]) -> List[DeadlineItem]:
        """Filter and adjust items based on feedback learning."""
        if not os.path.exists(self.feedback_file):
            return items
        
        filtered = []
        for item in items:
            if not self.should_filter_item(item):
                # Apply confidence penalty but don't filter
                penalty = self.calculate_confidence_penalty(item)
                if penalty > 0:
                    item.confidence = max(0.1, item.confidence - penalty)
                filtered.append(item)
        
        return filtered
    
    def clear_cache(self):
        """Clear cached stats (call after new feedback is added)."""
        self._cache = None


