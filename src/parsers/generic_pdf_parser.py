"""
Generic PDF Parser with text extraction.
"""
from pathlib import Path
from typing import List, Optional, Tuple
import re
from datetime import date

from src.models import Transaction, TransactionType, ProcessingResult
from src.parsers.base_parser import BaseParser


class GenericPDFParser(BaseParser):
    """Generic parser for PDF statements."""
    
    INSTITUTION = "generic"
    SUPPORTED_FORMATS = ["pdf"]
    
    def __init__(self, file_path: str, account_id: Optional[str] = None):
        super().__init__(file_path, account_id)
        self._text_content: Optional[str] = None
        self._pages: List[str] = []
        self._extraction_method: str = "none"
    
    def _extract_text_pdfplumber(self) -> Tuple[List[str], bool]:
        """Extract text using pdfplumber."""
        try:
            import pdfplumber
            
            pages = []
            with pdfplumber.open(str(self.file_path)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    pages.append(text)
            
            total_text = ' '.join(pages)
            if len(total_text.strip()) > 100:
                return pages, True
            
            return pages, False
            
        except ImportError:
            self.warnings.append("pdfplumber not installed")
            return [], False
        except Exception as e:
            self.warnings.append(f"pdfplumber extraction failed: {str(e)}")
            return [], False
    
    def _extract_text_pypdf2(self) -> Tuple[List[str], bool]:
        """Extract text using PyPDF2."""
        try:
            from PyPDF2 import PdfReader
            
            pages = []
            reader = PdfReader(str(self.file_path))
            for page in reader.pages:
                text = page.extract_text() or ""
                pages.append(text)
            
            total_text = ' '.join(pages)
            if len(total_text.strip()) > 100:
                return pages, True
            
            return pages, False
            
        except ImportError:
            self.warnings.append("PyPDF2 not installed")
            return [], False
        except Exception as e:
            self.warnings.append(f"PyPDF2 extraction failed: {str(e)}")
            return [], False
    
    def extract_text(self) -> bool:
        """Extract text from PDF using multiple methods."""
        # Try pdfplumber first
        pages, success = self._extract_text_pdfplumber()
        if success:
            self._pages = pages
            self._text_content = '\n\n'.join(pages)
            self._extraction_method = "pdfplumber"
            return True
        
        # Try PyPDF2 as fallback
        pages, success = self._extract_text_pypdf2()
        if success:
            self._pages = pages
            self._text_content = '\n\n'.join(pages)
            self._extraction_method = "pypdf2"
            return True
        
        return False
    
    def get_text(self) -> str:
        """Get the extracted text content."""
        if self._text_content is None:
            self.extract_text()
        return self._text_content or ""
    
    def _detect_bank(self, text: str) -> str:
        """Try to detect which bank this statement is from."""
        text_upper = text.upper()
        
        bank_patterns = [
            ('CHASE', 'JPMORGAN', 'chase'),
            ('CITI', 'CITIBANK', 'citi'),
            ('BANK OF AMERICA', 'BOFA', 'bofa'),
            ('WELLS FARGO', 'wells_fargo'),
            ('PNC BANK', 'PNC', 'pnc'),
            ('ROBINHOOD', 'robinhood'),
            ('US BANK', 'U.S. BANK', 'usbank'),
            ('CAPITAL ONE', 'capital_one'),
            ('DISCOVER', 'discover'),
            ('AMERICAN EXPRESS', 'AMEX', 'amex'),
        ]
        
        for patterns in bank_patterns:
            for pattern in patterns[:-1]:
                if pattern in text_upper:
                    return patterns[-1]
        
        return "generic"
    
    def _parse_transaction_line(self, line: str, year: int) -> Optional[Transaction]:
        """Try to parse a transaction from a line of text."""
        # Common date patterns
        date_patterns = [
            r'(\d{1,2}/\d{1,2}/\d{2,4})',  # MM/DD/YY or MM/DD/YYYY
            r'(\d{1,2}/\d{1,2})',           # MM/DD
            r'(\d{1,2}-\d{1,2}-\d{2,4})',   # MM-DD-YY
        ]
        
        # Amount pattern
        amount_pattern = r'(-?\$?[\d,]+\.\d{2}|\(\$?[\d,]+\.\d{2}\))'
        
        for date_pattern in date_patterns:
            date_match = re.search(date_pattern, line)
            if not date_match:
                continue
            
            date_str = date_match.group(1)
            
            # Add year if missing
            if date_str.count('/') == 1 or date_str.count('-') == 1:
                date_str = f"{date_str}/{year}"
            
            tx_date = self._parse_date(date_str)
            if not tx_date:
                continue
            
            # Find amounts
            amounts = re.findall(amount_pattern, line)
            if not amounts:
                continue
            
            # Take the last amount (usually the transaction amount)
            amount_str = amounts[-1]
            amount, tx_type = self._parse_amount(amount_str)
            
            if amount == 0:
                continue
            
            # Extract description (text between date and amount)
            start = date_match.end()
            last_amount_match = list(re.finditer(amount_pattern, line))[-1]
            end = last_amount_match.start()
            
            description = line[start:end].strip()
            description = re.sub(r'\s+', ' ', description)
            
            if len(description) < 3:
                continue
            
            return Transaction(
                id=self._generate_transaction_id(tx_date, description, amount),
                date=tx_date,
                description=self._clean_description(description),
                amount=amount,
                transaction_type=tx_type,
                account_id=self.account_id,
                institution=self.INSTITUTION,
                original_description=description,
                source_file=str(self.file_path),
                source_type="pdf"
            )
        
        return None
    
    def _get_statement_year(self, text: str) -> int:
        """Try to extract statement year from text."""
        from datetime import datetime
        
        # Look for year patterns
        year_patterns = [
            r'Statement\s+(?:Date|Period).*?(\d{4})',
            r'(\d{4})\s+Statement',
            r'as\s+of\s+\w+\s+\d{1,2},?\s+(\d{4})',
            r'(\d{4})',  # Fallback - any 4-digit number that looks like a year
        ]
        
        for pattern in year_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                year = int(match)
                if 2000 <= year <= 2030:
                    return year
        
        return datetime.now().year
    
    def parse_csv(self) -> ProcessingResult:
        """Not supported for PDF parser."""
        return ProcessingResult(
            file_path=str(self.file_path),
            file_type="csv",
            institution=self.INSTITUTION,
            account_type="unknown",
            success=False,
            errors=["PDF parser cannot handle CSV files"]
        )
    
    def parse_pdf(self) -> ProcessingResult:
        """Parse PDF statement."""
        if not self.extract_text():
            return ProcessingResult(
                file_path=str(self.file_path),
                file_type="pdf",
                institution=self.INSTITUTION,
                account_type="unknown",
                success=False,
                errors=["Could not extract text from PDF. Install pdfplumber or PyPDF2."],
                warnings=self.warnings
            )
        
        text = self.get_text()
        
        # Detect bank
        detected_bank = self._detect_bank(text)
        if detected_bank != "generic":
            self.INSTITUTION = detected_bank
        
        # Get statement year
        year = self._get_statement_year(text)
        
        # Parse transactions
        transactions = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if len(line) < 10:
                continue
            
            tx = self._parse_transaction_line(line, year)
            if tx:
                tx.institution = self.INSTITUTION
                transactions.append(tx)
        
        return ProcessingResult(
            file_path=str(self.file_path),
            file_type="pdf",
            institution=self.INSTITUTION,
            account_type="unknown",
            success=len(transactions) > 0,
            transactions=transactions,
            warnings=self.warnings
        )
    
    @classmethod
    def can_handle(cls, file_path: str) -> Tuple[bool, float]:
        """Check if this is a PDF file."""
        path = Path(file_path)
        
        if path.suffix.lower() != '.pdf':
            return False, 0.0
        
        # Generic PDF parser can handle any PDF
        return True, 0.3  # Low confidence - it's generic
