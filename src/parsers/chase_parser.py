"""
Chase Credit Card Statement Parser.
Parses Chase credit card PDF statements.
"""
import re
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import date

from src.models import Transaction, TransactionType, ProcessingResult
from src.parsers.base_parser import BaseParser


class ChaseParser(BaseParser):
    """Parser for Chase Credit Card PDF statements."""
    
    INSTITUTION = "chase"
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
        """Extract year from Chase statement."""
        # Look for Opening/Closing Date pattern: 04/23/26 - 05/22/26
        pattern = r'Opening/Closing Date\s+(\d{2})/(\d{2})/(\d{2})'
        match = re.search(pattern, text)
        if match:
            year = int(match.group(3))
            # Convert 2-digit year to 4-digit
            year = 2000 + year if year < 100 else year
            return year
        
        # Fallback: look for any year pattern
        year_match = re.search(r'20(\d{2})', text)
        if year_match:
            return 2000 + int(year_match.group(1))
        
        from datetime import datetime
        return datetime.now().year
    
    def _parse_transaction_line(self, line: str, year: int) -> Optional[Transaction]:
        """
        Parse a Chase transaction line.
        Format: MM/DD Description Amount
        Example: 04/22 TST*NAANIS CAFE Naperville IL 7.59
        """
        # Match pattern: date (MM/DD) followed by description and amount
        pattern = r'^(\d{2}/\d{2})\s+(.+?)\s+(-?\d+\.\d{2})$'
        match = re.match(pattern, line.strip())
        
        if not match:
            return None
        
        date_str = match.group(1)
        description = match.group(2).strip()
        amount_str = match.group(3)
        
        # Parse date
        try:
            month, day = map(int, date_str.split('/'))
            tx_date = date(year, month, day)
        except (ValueError, IndexError):
            return None
        
        # Parse amount - negative means credit (payment/refund)
        amount = float(amount_str)
        if amount < 0:
            tx_type = TransactionType.CREDIT
            amount = abs(amount)
        else:
            tx_type = TransactionType.DEBIT
        
        if amount == 0:
            return None
        
        return Transaction(
            id=self._generate_transaction_id(tx_date, description, amount),
            date=tx_date,
            description=self._clean_description(description),
            amount=amount,
            transaction_type=tx_type,
            account_id=self.account_id or "chase_credit",
            institution=self.INSTITUTION,
            original_description=description,
            source_file=str(self.file_path),
            source_type="pdf"
        )
    
    def parse_csv(self) -> ProcessingResult:
        """Parse Chase CSV export."""
        # Chase CSV typically has: Transaction Date, Post Date, Description, Category, Type, Amount
        transactions = []
        
        try:
            import csv
            
            with open(self.file_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    # Get date
                    date_str = row.get('Transaction Date') or row.get('Post Date', '')
                    tx_date = self._parse_date(date_str)
                    if not tx_date:
                        continue
                    
                    # Get description
                    description = row.get('Description', '').strip()
                    if not description:
                        continue
                    
                    # Get amount
                    amount_str = row.get('Amount', '0')
                    amount, tx_type = self._parse_amount(amount_str)
                    
                    if amount == 0:
                        continue
                    
                    tx = Transaction(
                        id=self._generate_transaction_id(tx_date, description, amount),
                        date=tx_date,
                        description=self._clean_description(description),
                        amount=amount,
                        transaction_type=tx_type,
                        account_id=self.account_id or "chase",
                        institution=self.INSTITUTION,
                        original_description=description,
                        source_file=str(self.file_path),
                        source_type="csv"
                    )
                    transactions.append(tx)
                    
        except Exception as e:
            return ProcessingResult(
                file_path=str(self.file_path),
                file_type="csv",
                institution=self.INSTITUTION,
                account_type="credit",
                success=False,
                errors=[f"CSV parsing error: {str(e)}"]
            )
        
        return ProcessingResult(
            file_path=str(self.file_path),
            file_type="csv",
            institution=self.INSTITUTION,
            account_type="credit",
            success=len(transactions) > 0,
            transactions=transactions,
            warnings=self.warnings
        )
    
    def parse_pdf(self) -> ProcessingResult:
        """Parse Chase Credit Card PDF statement."""
        if not self._extract_text():
            return ProcessingResult(
                file_path=str(self.file_path),
                file_type="pdf",
                institution=self.INSTITUTION,
                account_type="credit",
                success=False,
                errors=self.errors or ["Could not extract text from PDF"]
            )
        
        text = self._text_content
        year = self._get_statement_year(text)
        
        transactions = []
        in_transaction_section = False
        
        for page_text in self._pages:
            lines = page_text.split('\n')
            
            for line in lines:
                line = line.strip()
                
                # Detect transaction sections
                if 'ACCOUNT ACTIVITY' in line.upper():
                    in_transaction_section = True
                    continue
                
                if 'INTEREST CHARGE' in line.upper() or 'TOTALS YEAR-TO-DATE' in line.upper():
                    in_transaction_section = False
                    continue
                
                if not in_transaction_section:
                    continue
                
                # Skip headers
                if line.startswith('Date of') or 'Transaction' in line and 'Description' in line:
                    continue
                
                # Skip section headers
                if line in ['PAYMENTS AND OTHER CREDITS', 'PURCHASE', 'PURCHASES']:
                    continue
                
                tx = self._parse_transaction_line(line, year)
                if tx:
                    transactions.append(tx)
        
        return ProcessingResult(
            file_path=str(self.file_path),
            file_type="pdf",
            institution=self.INSTITUTION,
            account_type="credit",
            success=len(transactions) > 0,
            transactions=transactions,
            warnings=self.warnings
        )
    
    @classmethod
    def can_handle(cls, file_path: str) -> Tuple[bool, float]:
        """Check if this is a Chase statement."""
        path = Path(file_path)
        
        # Check filename
        if 'chase' in path.stem.lower():
            if path.suffix.lower() == '.pdf':
                return True, 0.9
            elif path.suffix.lower() == '.csv':
                return True, 0.85
        
        if path.suffix.lower() == '.pdf':
            try:
                import pdfplumber
                
                with pdfplumber.open(str(file_path)) as pdf:
                    if pdf.pages:
                        text = pdf.pages[0].extract_text() or ""
                        text_upper = text.upper()
                        
                        if 'CHASE' in text_upper and ('CREDIT' in text_upper or 'CARD' in text_upper):
                            return True, 0.95
                        if 'WWW.CHASE.COM' in text_upper:
                            return True, 0.9
            except:
                pass
        
        return False, 0.0
