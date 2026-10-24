"""
Citi Credit Card Statement Parser.
Parses Citi/Costco Anywhere Visa PDF statements.
"""
import re
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import date

from src.models import Transaction, TransactionType, ProcessingResult
from src.parsers.base_parser import BaseParser


class CitiParser(BaseParser):
    """Parser for Citi Credit Card PDF statements."""
    
    INSTITUTION = "citi"
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
        """Extract year from Citi statement."""
        # Look for Billing Period: MM/DD/YY-MM/DD/YY
        pattern = r'Billing Period:\s*(\d{2})/(\d{2})/(\d{2})'
        match = re.search(pattern, text)
        if match:
            year = int(match.group(3))
            return 2000 + year if year < 100 else year
        
        # Look for statement date patterns
        year_match = re.search(r'20(\d{2})', text)
        if year_match:
            return 2000 + int(year_match.group(1))
        
        from datetime import datetime
        return datetime.now().year
    
    def _parse_transaction_line(self, line: str, year: int) -> Optional[Transaction]:
        """
        Parse a Citi transaction line.
        Formats:
        - MM/DD Description Amount
        - MM/DD MM/DD Description Amount (Sale Date, Post Date)
        """
        # Try format: MM/DD MM/DD Description -$Amount or $Amount
        pattern1 = r'^(\d{2}/\d{2})\s+(\d{2}/\d{2})?\s*(.+?)\s+(-?\$[\d,]+\.\d{2})$'
        # Try format: MM/DD Description Amount (no dollar sign)
        pattern2 = r'^(\d{2}/\d{2})\s+(.+?)\s+(-?[\d,]+\.\d{2})$'
        
        match = re.match(pattern1, line.strip())
        if match:
            date_str = match.group(2) or match.group(1)  # Use post date if available
            description = match.group(3).strip()
            amount_str = match.group(4).replace('$', '').replace(',', '')
        else:
            match = re.match(pattern2, line.strip())
            if match:
                date_str = match.group(1)
                description = match.group(2).strip()
                amount_str = match.group(3).replace(',', '')
            else:
                return None
        
        # Parse date
        try:
            month, day = map(int, date_str.split('/'))
            tx_date = date(year, month, day)
        except (ValueError, IndexError):
            return None
        
        # Parse amount
        amount = float(amount_str)
        if amount < 0:
            tx_type = TransactionType.CREDIT
            amount = abs(amount)
        else:
            tx_type = TransactionType.DEBIT
        
        if amount == 0:
            return None
        
        # Skip internal Citi Flex entries
        if 'CITI FLEX' in description.upper():
            return None
        
        return Transaction(
            id=self._generate_transaction_id(tx_date, description, amount),
            date=tx_date,
            description=self._clean_description(description),
            amount=amount,
            transaction_type=tx_type,
            account_id=self.account_id or "citi_credit",
            institution=self.INSTITUTION,
            original_description=description,
            source_file=str(self.file_path),
            source_type="pdf"
        )
    
    def parse_csv(self) -> ProcessingResult:
        """Parse Citi CSV export."""
        transactions = []
        
        try:
            import csv
            
            with open(self.file_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    date_str = row.get('Date') or row.get('Transaction Date', '')
                    tx_date = self._parse_date(date_str)
                    if not tx_date:
                        continue
                    
                    description = row.get('Description', '').strip()
                    if not description:
                        continue
                    
                    # Citi uses Debit/Credit columns
                    debit = row.get('Debit', '').strip()
                    credit = row.get('Credit', '').strip()
                    
                    if debit:
                        amount, _ = self._parse_amount(debit)
                        tx_type = TransactionType.DEBIT
                    elif credit:
                        amount, _ = self._parse_amount(credit)
                        tx_type = TransactionType.CREDIT
                    else:
                        continue
                    
                    if amount == 0:
                        continue
                    
                    tx = Transaction(
                        id=self._generate_transaction_id(tx_date, description, amount),
                        date=tx_date,
                        description=self._clean_description(description),
                        amount=amount,
                        transaction_type=tx_type,
                        account_id=self.account_id or "citi",
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
        """Parse Citi Credit Card PDF statement."""
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
                if any(header in line for header in [
                    'Payments, Credits and Adjustments',
                    'Standard Purchases',
                    'CARDHOLDER SUMMARY'
                ]):
                    in_transaction_section = True
                    continue
                
                # End of transaction section
                if any(end in line for end in [
                    'Fees Charged',
                    'Interest Charged',
                    'TOTAL FEES',
                    'TOTAL INTEREST'
                ]):
                    in_transaction_section = False
                    continue
                
                if not in_transaction_section:
                    continue
                
                # Skip headers
                if 'Sale' in line and 'Post' in line and 'Date' in line:
                    continue
                if line.startswith('Date') and 'Description' in line:
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
        """Check if this is a Citi statement."""
        path = Path(file_path)
        
        # Check filename
        if 'citi' in path.stem.lower() or 'costco' in path.stem.lower():
            if path.suffix.lower() in ['.pdf', '.csv']:
                return True, 0.85
        
        if path.suffix.lower() == '.pdf':
            try:
                import pdfplumber
                
                with pdfplumber.open(str(file_path)) as pdf:
                    if pdf.pages:
                        text = pdf.pages[0].extract_text() or ""
                        text_upper = text.upper()
                        
                        if 'CITI' in text_upper or 'CITIBANK' in text_upper:
                            return True, 0.95
                        if 'COSTCO ANYWHERE VISA' in text_upper:
                            return True, 0.95
                        if 'WWW.CITICARDS.COM' in text_upper:
                            return True, 0.9
            except:
                pass
        
        return False, 0.0
