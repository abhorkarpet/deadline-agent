import json
from datetime import datetime
from typing import List, Optional

from .models import DeadlineItem, EmailMessageData

try:
    from openai import OpenAI
    from openai import APIError as OpenAIAPIError
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAIAPIError = Exception


class InsufficientFundsError(Exception):
    """Raised when OpenAI API fails due to insufficient funds or billing issues."""
    pass


EXTRACTION_PROMPT = """You are an expert at extracting deadline information from emails.

Analyze this email and extract ONLY actionable deadlines where the user must take action by a specific date to avoid charges, cancellations, or loss of benefits.

EXTRACT deadlines related to:
- Subscription renewals or cancellations (user must cancel by date X to avoid charge)
- Free trial end dates (trial expires on date X, user will be charged if not cancelled)
- Refund/cancellation deadlines (user can cancel/refund by date X)
- Billing dates (payment will be processed on date X)
- Travel/hotel booking cancellation deadlines (user can cancel booking for refund by date X)

CRITICAL RULES - DO NOT EXTRACT:
1. Promotional/marketing content:
   - Loyalty program promotions ("Earn status by staying X nights")
   - Marketing campaign deadlines
   - Promotional offers or deals
   - Discount expiration dates
   - Limited-time sales or special offers

2. Informational-only dates:
   - Dates when changes become effective (but no action required)
   - Dates when services start (but no cancellation deadline)
   - Investment changes effective dates (informational only)
   - Policy updates or notices (no deadline for action)

3. Incorrect categorization:
   - Do NOT mark as "travel" unless there's an actual hotel/flight booking with cancellation deadline
   - Do NOT mark as "subscription" unless there's an actual subscription renewal or cancellation deadline
   - Verify the category matches the actual content

4. Shopping/retail offers:
   - "Sale ends tomorrow"
   - "50% off expires Jan 5"
   - "Limited time offer"
   - Any retail/promotional expiration dates

Email subject: {subject}
Email sender: {sender}
Email date: {email_date}
Email content:
{content}

Return a JSON array of deadline objects. Each object should have:
- "deadline_at": ISO 8601 date string (e.g., "2025-01-15T00:00:00")
- "title": Brief description (e.g., "Netflix subscription renews")
- "category": One of: "subscription" (renewals/cancellations), "trial" (free trial ends), "travel" (hotel/flight cancellations), "billing" (payment dates), "refund" (refund deadlines), "general" (other actionable deadlines)
- "confidence": 0.0-1.0 based on how explicit and actionable the deadline is (reduce confidence for promotional content, informational dates, or ambiguous deadlines)
- "summary": A brief 1-2 sentence summary explaining what action is required by the deadline

Examples of what to extract:
- "Your subscription renews on January 15, 2025. Cancel before then to avoid charges." → {{"deadline_at": "2025-01-15T00:00:00", "title": "Subscription renewal", "category": "subscription", "confidence": 0.9, "summary": "Subscription will automatically renew on January 15, 2025. Cancel before this date to avoid charges."}}
- Invoice showing "Next billing: Feb 1" → {{"deadline_at": "2025-02-01T00:00:00", "title": "Next billing date", "category": "billing", "confidence": 0.8, "summary": "Next payment will be processed on February 1, 2025"}}
- "Cancel hotel by Jan 10 for full refund" → {{"deadline_at": "2025-01-10T00:00:00", "title": "Hotel cancellation deadline", "category": "travel", "confidence": 0.9, "summary": "Hotel booking can be cancelled for full refund until January 10, 2025"}}
- "Free trial ends February 5" → {{"deadline_at": "2025-02-05T00:00:00", "title": "Free trial ends", "category": "trial", "confidence": 0.9, "summary": "Free trial period expires on February 5, 2025. Cancel before then to avoid charges."}}

Examples of what NOT to extract:
- "Earn Diamond status by staying 10 nights by Dec 15" → [] (promotional/loyalty program)
- "Investment changes effective Jan 1" → [] (informational only, no action required)
- "Sale ends tomorrow" → [] (shopping promotion)
- "Hotel booking" email with no cancellation deadline mentioned → [] (no actionable deadline)

If there are NO actionable deadlines (only promotional content, informational dates, or shopping offers), return an empty array: []

Return ONLY valid JSON, no other text.
"""


class LLMExtractor:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        if not OPENAI_AVAILABLE:
            raise ImportError("openai package not installed. Run: pip install openai")
        if not api_key:
            raise ValueError("LLM API key is required")
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def extract_from_message(self, msg: EmailMessageData) -> List[DeadlineItem]:
        """Extract deadlines using LLM."""
        # Combine text content (limit to avoid token limits)
        content = (msg.text or "")[:4000]  # Limit for cost/token efficiency
        if msg.html:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(msg.html[:4000], "html.parser")
            for tag in soup(["script", "style"]):
                tag.extract()
            html_text = soup.get_text(" ", strip=True)
            content = content + "\n" + html_text[:2000]
        
        if not content.strip():
            return []

        email_date_str = (msg.date or datetime.utcnow()).strftime("%Y-%m-%d")
        
        prompt = EXTRACTION_PROMPT.format(
            subject=msg.subject or "",
            sender=msg.sender or "",
            email_date=email_date_str,
            content=content[:3000],  # Final limit
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a precise deadline extraction assistant. Always return valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,  # Low temperature for consistency
                max_tokens=500,
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Clean up - remove markdown code blocks if present
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
                result_text = result_text.strip()
            
            parsed = json.loads(result_text)
            
            if not isinstance(parsed, list):
                return []
            
            items = []
            for item_data in parsed:
                try:
                    deadline_at = datetime.fromisoformat(item_data["deadline_at"].replace("Z", "+00:00"))
                    # Remove timezone for consistency with other extractors
                    if deadline_at.tzinfo:
                        deadline_at = deadline_at.replace(tzinfo=None)
                    
                    category = item_data.get("category", "general").lower()
                    # Filter out shopping offers - reduce confidence and skip low-confidence items
                    confidence = float(item_data.get("confidence", 0.7))
                    if confidence < 0.5:
                        continue  # Skip low confidence items (likely shopping offers)
                    
                    # Get excerpt from original content 
                    email_excerpt = None
                    # Try to get text content for excerpt
                    content = msg.text or ""
                    if not content and msg.html:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(msg.html[:2000], "html.parser")
                        for tag in soup(["script", "style"]):
                            tag.extract()
                        content = soup.get_text(" ", strip=True)
                    
                    if content:
                        # Use first 400 chars as excerpt, try to end at sentence boundary
                        excerpt = content[:400].strip()
                        # Find last sentence boundary
                        last_period = excerpt.rfind('.')
                        if last_period > 200:
                            excerpt = excerpt[:last_period + 1]
                        email_excerpt = excerpt if excerpt else None
                    
                    # Get LLM-generated summary if available
                    email_summary = item_data.get("summary")
                    
                    items.append(
                        DeadlineItem(
                            deadline_at=deadline_at,
                            title=item_data.get("title", msg.subject or "Deadline"),
                            source=f"email:{msg.sender}",
                            link=None,
                            confidence=confidence,
                            context=None,  # LLM already saw full context
                            category=category,
                            email_date=msg.date,
                            email_excerpt=email_excerpt,
                            email_summary=email_summary,
                        )
                    )
                except (KeyError, ValueError, TypeError) as e:
                    # Skip invalid items
                    continue
            
            return items
        except json.JSONDecodeError:
            # LLM didn't return valid JSON, return empty
            return []
        except OpenAIAPIError as e:
            # Check for insufficient funds/billing errors
            error_code = getattr(e, 'code', None) or ""
            error_message = str(e).lower()
            
            # Common OpenAI error codes/messages for insufficient funds
            insufficient_funds_indicators = [
                "insufficient_quota",
                "billing_not_active",
                "insufficient",
                "quota",
                "billing",
                "payment",
                "funds",
                "credit",
            ]
            
            if any(indicator in error_code.lower() or indicator in error_message for indicator in insufficient_funds_indicators):
                raise InsufficientFundsError(
                    f"OpenAI API error: {str(e)}. "
                    "Your account may have insufficient funds or billing is not active. "
                    "Please add funds to your OpenAI account to continue."
                ) from e
            # For other API errors, return empty (don't fail the whole scan)
            return []
        except Exception as e:
            # Other unexpected errors - return empty to not break the scan
            return []

