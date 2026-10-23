"""
Base parser class that all institution-specific parsers inherit from.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import date
import hashlib
import re

from src.models import Transaction, TransactionType, ProcessingResult


class BaseParser(ABC):
    """Base class for all statement parsers."""
    
    INSTITUTION: str = ""
    ACCOUNT_TYPES: List[str] = []
    SUPPORTED_FORMATS: List[str] = ["csv", "pdf"]
    
    def __init__(self, file_path: str, account_id: Optional[str] = None):
        self.file_path = Path(file_path)
        self.account_id = account_id or self._generate_account_id()
        self.transactions: List[Transaction] = []
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def _generate_account_id(self) -> str:
        """Generate account ID from filename if not provided."""
        filename = self.file_path.stem.lower()
        return f"{self.INSTITUTION}_{filename}"
    
    def _generate_transaction_id(self, tx_date: date, description: str, amount: float) -> str:
        """Generate unique transaction ID based on content."""
        content = f"{tx_date.isoformat()}|{description}|{amount}|{self.account_id}"
        return hashlib.md5(content.encode()).hexdigest()[:12]
    
    def _parse_amount(self, amount_str: str) -> Tuple[float, TransactionType]:
        """Parse amount string and determine transaction type."""
        # Remove currency symbols, commas, and whitespace
        cleaned = re.sub(r'[$,\s]', '', str(amount_str))
        
        # Handle parentheses as negative (common in financial statements)
        if cleaned.startswith('(') and cleaned.endswith(')'):
            cleaned = '-' + cleaned[1:-1]
        
        try:
            amount = float(cleaned)
            if amount < 0:
                return abs(amount), TransactionType.DEBIT
            else:
                return amount, TransactionType.CREDIT
        except ValueError:
            self.errors.append(f"Could not parse amount: {amount_str}")
            return 0.0, TransactionType.DEBIT
    
    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse date string in various formats."""
        from dateutil import parser as date_parser
        
        try:
            parsed = date_parser.parse(date_str)
            return parsed.date()
        except (ValueError, TypeError):
            self.errors.append(f"Could not parse date: {date_str}")
            return None
    
    def _clean_description(self, description: str) -> str:
        """Clean and normalize transaction description."""
        if not description:
            return ""
        
        # Remove extra whitespace
        cleaned = ' '.join(description.split())
        
        # Remove common prefixes
        prefixes_to_remove = [
            'DEBIT CARD PURCHASE',
            'CREDIT CARD PURCHASE', 
            'POS PURCHASE',
            'POINT OF SALE',
            'RECURRING PAYMENT',
            'AUTOMATIC PAYMENT',
            'ACH DEBIT',
            'ACH CREDIT',
            'ONLINE TRANSFER',
            'CHECKCARD',
            'VISA PURCHASE',
            'MASTERCARD PURCHASE',
        ]
        
        upper_cleaned = cleaned.upper()
        for prefix in prefixes_to_remove:
            if upper_cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                upper_cleaned = cleaned.upper()
        
        # Remove date patterns from description (often embedded)
        cleaned = re.sub(r'\s+\d{2}/\d{2}\s*', ' ', cleaned)
        
        # Remove extra whitespace again
        cleaned = ' '.join(cleaned.split())
        
        return cleaned.strip()
    
    @abstractmethod
    def parse_csv(self) -> ProcessingResult:
        """Parse CSV format statement."""
        pass
    
    @abstractmethod
    def parse_pdf(self) -> ProcessingResult:
        """Parse PDF format statement."""
        pass
    
    def parse(self) -> ProcessingResult:
        """Main parsing method - auto-detects format."""
        suffix = self.file_path.suffix.lower()
        
        if suffix == '.csv':
            return self.parse_csv()
        elif suffix == '.pdf':
            return self.parse_pdf()
        elif suffix in ['.xlsx', '.xls']:
            return self.parse_excel()
        else:
            return ProcessingResult(
                file_path=str(self.file_path),
                file_type="unknown",
                institution=self.INSTITUTION,
                account_type="unknown",
                success=False,
                errors=[f"Unsupported file format: {suffix}"]
            )
    
    def parse_excel(self) -> ProcessingResult:
        """Parse Excel file - convert to CSV and parse."""
        try:
            import pandas as pd
            df = pd.read_excel(str(self.file_path))
            # Save as temp CSV and parse
            temp_csv = self.file_path.with_suffix('.csv')
            df.to_csv(temp_csv, index=False)
            self.file_path = temp_csv
            result = self.parse_csv()
            # Clean up temp file
            temp_csv.unlink()
            return result
        except Exception as e:
            return ProcessingResult(
                file_path=str(self.file_path),
                file_type="excel",
                institution=self.INSTITUTION,
                account_type="unknown",
                success=False,
                errors=[f"Excel parsing error: {str(e)}"]
            )
    
    @classmethod
    def can_handle(cls, file_path: str) -> Tuple[bool, float]:
        """
        Check if this parser can handle the given file.
        Returns (can_handle, confidence_score).
        Subclasses should override to implement institution detection.
        """
        return False, 0.0
