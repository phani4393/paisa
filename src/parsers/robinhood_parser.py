"""
Robinhood Statement Parser.
Parses Robinhood Cash Card spending statements (PDF) and
Robinhood credit card transaction exports (CSV).
"""
import csv
import re
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import date

from src.models import Transaction, TransactionType, ProcessingResult
from src.parsers.base_parser import BaseParser


class RobinhoodParser(BaseParser):
    """Parser for Robinhood statements (PDF spending statements + CSV card exports)."""
    
    INSTITUTION = "robinhood"
    SUPPORTED_FORMATS = ["pdf", "csv"]
    
    # Columns that identify a Robinhood credit-card CSV export.
    # Header: Date,Time,Cardholder,Amount,Points,Balance,Status,Type,Merchant,Description
    CSV_SIGNATURE_COLUMNS = {"date", "amount", "type", "merchant", "points"}
    
    # Transaction "Type" values that represent money returning to the account
    # (credits), regardless of amount sign.
    CSV_CREDIT_TYPES = {"refund", "return", "payment", "credit", "reversal"}
    # Types that are card payments / transfers rather than real income.
    CSV_TRANSFER_TYPES = {"payment"}
    
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
        """
        Parse a Robinhood credit-card CSV export.

        Expected header:
            Date,Time,Cardholder,Amount,Points,Balance,Status,Type,Merchant,Description

        Sign convention in this format:
          - Purchases/Fees have a POSITIVE amount  -> money out  -> DEBIT
          - Refunds/Payments have a NEGATIVE amount -> money in   -> CREDIT
        The "Type" column is authoritative for direction, so we use it rather
        than relying on the sign alone. Card "Payment" rows are marked as
        transfers so they are not counted as income.
        """
        transactions: List[Transaction] = []

        try:
            with open(self.file_path, 'r', encoding='utf-8-sig', newline='') as f:
                reader = csv.DictReader(f)

                if reader.fieldnames is None:
                    return self._csv_error("CSV has no header row")

                # Build a case-insensitive map of column name -> actual header
                cols = {name.lower().strip(): name for name in reader.fieldnames}

                required = ("date", "amount")
                missing = [c for c in required if c not in cols]
                if missing:
                    return self._csv_error(
                        f"Robinhood CSV missing expected column(s): {', '.join(missing)}"
                    )

                date_col = cols["date"]
                amount_col = cols["amount"]
                type_col = cols.get("type")
                merchant_col = cols.get("merchant")
                desc_col = cols.get("description")
                status_col = cols.get("status")

                for row_num, row in enumerate(reader, start=2):
                    try:
                        tx = self._parse_csv_row(
                            row, row_num, date_col, amount_col,
                            type_col, merchant_col, desc_col, status_col
                        )
                        if tx:
                            transactions.append(tx)
                    except Exception as e:
                        self.warnings.append(f"Row {row_num}: {e}")

        except Exception as e:
            return self._csv_error(f"CSV parsing error: {e}")

        return ProcessingResult(
            file_path=str(self.file_path),
            file_type="csv",
            institution=self.INSTITUTION,
            account_type="credit_card",
            success=len(transactions) > 0,
            transactions=transactions,
            warnings=self.warnings,
        )

    def _parse_csv_row(
        self, row, row_num, date_col, amount_col,
        type_col, merchant_col, desc_col, status_col
    ) -> Optional[Transaction]:
        """Convert a single Robinhood CSV row into a Transaction (or None to skip)."""
        date_str = (row.get(date_col) or "").strip()
        amount_str = (row.get(amount_col) or "").strip()
        if not date_str or not amount_str:
            return None

        tx_date = self._parse_date(date_str)
        if not tx_date:
            return None

        # Parse the raw signed amount (keep the sign so we can read direction).
        cleaned = re.sub(r'[$,\s]', '', amount_str)
        if cleaned.startswith('(') and cleaned.endswith(')'):
            cleaned = '-' + cleaned[1:-1]
        try:
            signed_amount = float(cleaned)
        except ValueError:
            self.warnings.append(f"Row {row_num}: could not parse amount {amount_str!r}")
            return None

        if signed_amount == 0:
            return None

        tx_type_raw = (row.get(type_col) or "").strip().lower() if type_col else ""

        # Determine direction. Prefer the explicit Type; fall back to the sign.
        # In this export: negative amount = money back (credit), positive = spend (debit).
        if tx_type_raw in self.CSV_CREDIT_TYPES or signed_amount < 0:
            tx_type = TransactionType.CREDIT
        else:
            tx_type = TransactionType.DEBIT

        amount = abs(signed_amount)

        # Description: prefer the raw bank Description, fall back to Merchant.
        description = ""
        if desc_col:
            description = (row.get(desc_col) or "").strip()
        if not description and merchant_col:
            description = (row.get(merchant_col) or "").strip()
        if not description:
            description = "Robinhood transaction"

        tx = Transaction(
            id=self._generate_transaction_id(tx_date, description, amount),
            date=tx_date,
            description=self._clean_description(description),
            amount=amount,
            transaction_type=tx_type,
            account_id=self.account_id or "robinhood_card",
            institution=self.INSTITUTION,
            original_description=description,
            source_file=str(self.file_path),
            source_type="csv",
        )

        # Card payments are transfers, not income/spending.
        if tx_type_raw in self.CSV_TRANSFER_TYPES:
            tx.category = "Transfer"
            tx.is_transfer = True

        return tx

    def _csv_error(self, message: str) -> ProcessingResult:
        """Build a failed CSV ProcessingResult with a single error message."""
        return ProcessingResult(
            file_path=str(self.file_path),
            file_type="csv",
            institution=self.INSTITUTION,
            account_type="credit_card",
            success=False,
            errors=[message],
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
        """Check if this is a Robinhood statement (PDF) or card export (CSV)."""
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix == '.pdf':
            return cls._can_handle_pdf(path)
        if suffix == '.csv':
            return cls._can_handle_csv(path)
        return False, 0.0

    @classmethod
    def _can_handle_pdf(cls, path: Path) -> Tuple[bool, float]:
        """Detect a Robinhood spending-statement PDF."""
        # Check filename
        if 'robinhood' in path.stem.lower():
            return True, 0.9

        # Try to read and detect
        try:
            import pdfplumber

            with pdfplumber.open(str(path)) as pdf:
                if pdf.pages:
                    text = pdf.pages[0].extract_text() or ""
                    text_upper = text.upper()

                    if 'ROBINHOOD' in text_upper and 'SPENDING' in text_upper:
                        return True, 0.95
                    if 'ROBINHOOD CASH CARD' in text_upper:
                        return True, 0.95
        except Exception:
            pass

        return False, 0.0

    @classmethod
    def _can_handle_csv(cls, path: Path) -> Tuple[bool, float]:
        """
        Detect a Robinhood credit-card CSV by its header signature.
        The distinctive combination of columns (Amount + Type + Merchant +
        Points) is unique to the Robinhood card export among the banks we
        support, so this wins over the generic CSV parser.
        """
        try:
            with open(path, 'r', encoding='utf-8-sig', newline='') as f:
                reader = csv.reader(f)
                headers = next(reader, None)
            if not headers:
                return False, 0.0

            header_set = {h.lower().strip() for h in headers}
            if cls.CSV_SIGNATURE_COLUMNS.issubset(header_set):
                # High confidence: the "Points" column in particular is
                # specific to the Robinhood card.
                return True, 0.95
        except Exception:
            pass

        return False, 0.0
