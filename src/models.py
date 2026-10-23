"""
Data models for Paisa.
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, List, Dict
from enum import Enum
import json


class TransactionType(Enum):
    DEBIT = "debit"
    CREDIT = "credit"


@dataclass
class Transaction:
    """Represents a single financial transaction."""
    id: str
    date: date
    description: str
    amount: float
    transaction_type: TransactionType
    account_id: str
    institution: str
    
    # Classification
    category: str = "Uncategorized"
    merchant_name: str = ""
    
    # Metadata
    original_description: str = ""
    is_transfer: bool = False
    is_recurring: bool = False
    
    # Source tracking
    source_file: str = ""
    source_type: str = ""  # csv, pdf
    
    # User modifications
    user_categorized: bool = False
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "date": self.date.isoformat(),
            "description": self.description,
            "amount": self.amount,
            "transaction_type": self.transaction_type.value,
            "account_id": self.account_id,
            "institution": self.institution,
            "category": self.category,
            "merchant_name": self.merchant_name,
            "original_description": self.original_description,
            "is_transfer": self.is_transfer,
            "is_recurring": self.is_recurring,
            "source_file": self.source_file,
            "source_type": self.source_type,
            "user_categorized": self.user_categorized
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Transaction':
        return cls(
            id=data["id"],
            date=date.fromisoformat(data["date"]) if isinstance(data["date"], str) else data["date"],
            description=data["description"],
            amount=data["amount"],
            transaction_type=TransactionType(data["transaction_type"]),
            account_id=data["account_id"],
            institution=data["institution"],
            category=data.get("category", "Uncategorized"),
            merchant_name=data.get("merchant_name", ""),
            original_description=data.get("original_description", ""),
            is_transfer=data.get("is_transfer", False),
            is_recurring=data.get("is_recurring", False),
            source_file=data.get("source_file", ""),
            source_type=data.get("source_type", ""),
            user_categorized=data.get("user_categorized", False)
        )


@dataclass
class Rule:
    """Categorization rule."""
    id: int
    pattern: str  # Text pattern to match in description
    category: str
    created_at: datetime = field(default_factory=datetime.now)
    match_count: int = 0
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "pattern": self.pattern,
            "category": self.category,
            "created_at": self.created_at.isoformat(),
            "match_count": self.match_count
        }


@dataclass 
class ProcessingResult:
    """Result of processing a single file."""
    file_path: str
    file_type: str  # csv, pdf
    institution: str
    account_type: str
    success: bool
    transactions: List[Transaction] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# Default categories
DEFAULT_CATEGORIES = [
    {"name": "Income", "icon": "💰", "color": "#10b981"},
    {"name": "Housing", "icon": "🏠", "color": "#ef4444"},
    {"name": "Groceries", "icon": "🛒", "color": "#f59e0b"},
    {"name": "Dining", "icon": "🍽️", "color": "#8b5cf6"},
    {"name": "Auto", "icon": "🚗", "color": "#3b82f6"},
    {"name": "Gas", "icon": "⛽", "color": "#06b6d4"},
    {"name": "Utilities", "icon": "💡", "color": "#84cc16"},
    {"name": "Subscriptions", "icon": "📱", "color": "#10b981"},
    {"name": "Shopping", "icon": "🛍️", "color": "#ec4899"},
    {"name": "Health", "icon": "💊", "color": "#14b8a6"},
    {"name": "Entertainment", "icon": "🎬", "color": "#a855f7"},
    {"name": "Travel", "icon": "✈️", "color": "#0ea5e9"},
    {"name": "Insurance", "icon": "🛡️", "color": "#64748b"},
    {"name": "Fees", "icon": "💸", "color": "#dc2626"},
    {"name": "ATM", "icon": "🏧", "color": "#737373"},
    {"name": "Transfer", "icon": "🔄", "color": "#6b7280"},
    {"name": "Other", "icon": "📦", "color": "#9ca3af"},
    {"name": "Uncategorized", "icon": "❓", "color": "#f59e0b"},
]

# Default categorization rules
DEFAULT_RULES = [
    # Income
    ("DIRECT DEP", "Income"),
    ("PAYROLL", "Income"),
    ("SALARY", "Income"),
    ("PAYCHECK", "Income"),
    
    # Groceries
    ("COSTCO", "Groceries"),
    ("WALMART", "Groceries"),
    ("TARGET", "Groceries"),
    ("KROGER", "Groceries"),
    ("ALDI", "Groceries"),
    ("JEWEL", "Groceries"),
    ("WHOLE FOODS", "Groceries"),
    ("TRADER JOE", "Groceries"),
    ("PATEL BROTHERS", "Groceries"),
    ("INDIAN GROCERS", "Groceries"),
    
    # Dining
    ("DUNKIN", "Dining"),
    ("STARBUCKS", "Dining"),
    ("MCDONALD", "Dining"),
    ("CHIPOTLE", "Dining"),
    ("SUBWAY", "Dining"),
    ("UBER EATS", "Dining"),
    ("DOORDASH", "Dining"),
    ("GRUBHUB", "Dining"),
    ("RESTAURANT", "Dining"),
    
    # Gas
    ("SHELL", "Gas"),
    ("EXXON", "Gas"),
    ("BP ", "Gas"),
    ("CHEVRON", "Gas"),
    ("SPEEDWAY", "Gas"),
    ("GAS STATION", "Gas"),
    
    # Auto
    ("JIFFY LUBE", "Auto"),
    ("AUTO ZONE", "Auto"),
    ("CAR WASH", "Auto"),
    ("PARKING", "Auto"),
    ("TOLL", "Auto"),
    
    # Subscriptions
    ("NETFLIX", "Subscriptions"),
    ("SPOTIFY", "Subscriptions"),
    ("APPLE.COM/BILL", "Subscriptions"),
    ("AMAZON PRIME", "Subscriptions"),
    ("HULU", "Subscriptions"),
    ("DISNEY+", "Subscriptions"),
    ("HBO", "Subscriptions"),
    ("YOUTUBE", "Subscriptions"),
    ("WILLOW TV", "Subscriptions"),
    ("ADOBE", "Subscriptions"),
    
    # Utilities
    ("COMED", "Utilities"),
    ("NICOR", "Utilities"),
    ("COMCAST", "Utilities"),
    ("XFINITY", "Utilities"),
    ("T-MOBILE", "Utilities"),
    ("VERIZON", "Utilities"),
    ("AT&T", "Utilities"),
    
    # Shopping
    ("AMAZON", "Shopping"),
    ("TEMU", "Shopping"),
    ("EBAY", "Shopping"),
    ("BEST BUY", "Shopping"),
    ("HOME DEPOT", "Shopping"),
    ("LOWES", "Shopping"),
    ("MENARDS", "Shopping"),
    
    # Health
    ("PHARMACY", "Health"),
    ("CVS", "Health"),
    ("WALGREENS", "Health"),
    ("MEDICAL", "Health"),
    ("DOCTOR", "Health"),
    ("HOSPITAL", "Health"),
    
    # Transfers
    ("TRANSFER", "Transfer"),
    ("ZELLE", "Transfer"),
    ("VENMO", "Transfer"),
    ("PAYMENT THANK YOU", "Transfer"),
    ("AUTOPAY", "Transfer"),
    ("CREDIT CARD PAYMENT", "Transfer"),
    
    # Fees
    ("ATM FEE", "Fees"),
    ("SERVICE CHARGE", "Fees"),
    ("OVERDRAFT", "Fees"),
    ("MONTHLY FEE", "Fees"),
    
    # ATM
    ("ATM WITHDRAWAL", "ATM"),
    ("ATM ", "ATM"),
]
