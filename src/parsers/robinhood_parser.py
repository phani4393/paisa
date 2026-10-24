"""
Robinhood Spending Statement Parser.
Parses Robinhood Cash Card spending statements.
"""
import re
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import date

from src.models import Transaction, TransactionType, ProcessingResult
from src.parsers.base_parser import BaseParser


class RobinhoodParser(BaseParser):
    """Parser for Robinhood Spending Statement PDFs."""
    
    INSTITUTION = "robinhood"
    SUPPORTED_FORMATS = ["pdf"]
    
    def __init__(self, file_path: str, account_id: Optional[str] = None):
        super().__init__(file_path, account_id)
        self._text_content: Optional[str] = None
        self._pages: List[str] = []
    
    def _extract_text(self) -> bool:
        """Extract text from PDF using pdfplumber."""
        try:
            import pdfplumber
            
            pages = []
            with pdfplumber.open(str(self.file_path)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    pages.append(text)
            
            self._pages = pages
            self._text_content = '\n\n'.join(pages)
            return len(self._text_content.strip()) > 100
            
        except Exception as e:
            self.errors.append(f"PDF extraction failed: {str(e)}")
            return False
    
    def _get_statement_year(self, text: str) -> int:
        """Extract year from Robinhood statement."""
        # Look for patterns like "05-2026" or "May 2026"
        year_patterns = [
            r'(\d{2})-(\d{4})',  # MM-YYYY
            r'(\w+)\s+(\d{4})',  # Month YYYY
        ]
        
        for pattern in year_patterns:
            match = re.search(pattern, text)
            if match:
                year = int(match.group(2)) if len(match.groups()) >= 2 else int(match.group(1))
                if 2020 <= year <= 2030:
                    return year
        
        from datetime import datetime
        return datetime.now().year
    
    def _parse_transaction_line(self, line: str, year: int) -> Optional[Transaction]:
        """
        Parse a Robinhood transaction line.
        Format: DESCRIPTION DATE CREDIT DEBIT
        Example: Voya NOA 05-04-2026 -- $95.65
        """
        # Match pattern: description, date (MM-DD-YYYY), optional credit, optional debit
        # Robinhood format: DESCRIPTION TYPE? DATE CREDIT DEBIT
        # Where credit/debit can be "$amount" or "--"
        
        pattern = r'^(.+?)\s+(\d{2}-\d{2}-\d{4})\s+(\$[\d,]+\.\d{2}|--)\s+(\$[\d,]+\.\d{2}|--)$'
        match = re.match(pattern, line.strip())
        
        if not match:
            return None
        
        description = match.group(1).strip()
        date_str = match.group(2)
        credit_str = match.group(3)
        debit_str = match.group(4)
        
        # Parse date (MM-DD-YYYY)
        try:
            parts = date_str.split('-')
            tx_date = date(int(parts[2]), int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            return None
        
        # Determine amount and type
        if credit_str != '--':
            amount_str = credit_str.replace('$', '').replace(',', '')
            amount = float(amount_str)
            tx_type = TransactionType.CREDIT
        elif debit_str != '--':
            amount_str = debit_str.replace('$', '').replace(',', '')
            amount = float(amount_str)
            tx_type = TransactionType.DEBIT
        else:
            return None
        
        if amount == 0:
            return None
        
        # Extract transaction type from description (NOA, CARD, PDA, etc.)
        # Remove type suffix for cleaner description
        clean_desc = re.sub(r'\s+(NOA|CARD|PDA|XENT)\s*$', '', description)
        
        return Transaction(
            id=self._generate_transaction_id(tx_date, description, amount),
            date=tx_date,
            description=self._clean_description(clean_desc),
            amount=amount,
            transaction_type=tx_type,
            account_id=self.account_id or "robinhood_spending",
            institution=self.INSTITUTION,
            original_description=description,
            source_file=str(self.file_path),
            source_type="pdf"
        )
    
    def parse_csv(self) -> ProcessingResult:
        """Not supported for Robinhood parser."""
        return ProcessingResult(
            file_path=str(self.file_path),
            file_type="csv",
            institution=self.INSTITUTION,
            account_type="spending",
            success=False,
            errors=["Robinhood parser only supports PDF files"]
        )
    
    def parse_pdf(self) -> ProcessingResult:
        """Parse Robinhood Spending Statement PDF."""
        if not self._extract_text():
            return ProcessingResult(
                file_path=str(self.file_path),
                file_type="pdf",
                institution=self.INSTITUTION,
                account_type="spending",
                success=False,
                errors=self.errors or ["Could not extract text from PDF"]
            )
        
        text = self._text_content
        year = self._get_statement_year(text)
        
        transactions = []
        
        # Process each page
        for page_text in self._pages:
            lines = page_text.split('\n')
            
            for line in lines:
                line = line.strip()
                if len(line) < 15:
                    continue
                
                # Skip header lines
                if line.startswith('DESCRIPTION') or 'TRANSACTION DATE' in line:
                    continue
                
                # Skip boilerplate text
                if 'Robinhood' in line and 'Cash Card' in line:
                    continue
                if 'Your use of the' in line:
                    continue
                
                tx = self._parse_transaction_line(line, year)
                if tx:
                    transactions.append(tx)
        
        return ProcessingResult(
            file_path=str(self.file_path),
            file_type="pdf",
            institution=self.INSTITUTION,
            account_type="spending",
            success=len(transactions) > 0,
            transactions=transactions,
            warnings=self.warnings
        )
    
    @classmethod
    def can_handle(cls, file_path: str) -> Tuple[bool, float]:
        """Check if this is a Robinhood statement."""
        path = Path(file_path)
        
        if path.suffix.lower() != '.pdf':
            return False, 0.0
        
        # Check filename
        if 'robinhood' in path.stem.lower():
            return True, 0.9
        
        # Try to read and detect
        try:
            import pdfplumber
            
            with pdfplumber.open(str(file_path)) as pdf:
                if pdf.pages:
                    text = pdf.pages[0].extract_text() or ""
                    text_upper = text.upper()
                    
                    if 'ROBINHOOD' in text_upper and 'SPENDING' in text_upper:
                        return True, 0.95
                    if 'ROBINHOOD CASH CARD' in text_upper:
                        return True, 0.95
        except:
            pass
        
        return False, 0.0
