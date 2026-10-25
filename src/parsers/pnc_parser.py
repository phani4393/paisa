"""
PNC Bank Statement Parser.

Parses PNC "Virtual Wallet" / checking statement PDFs. PNC groups activity
into labelled sections, and the transaction direction depends on which section
a row is in:

  Credits (money in):
    - "Deposits and Other Additions"

  Debits (money out):
    - "Banking/Debit Card Withdrawals and Purchases"
    - "Online and Electronic Banking Deductions"
    - "Checks and Substitute Checks"

Each transaction row looks like:  MM/DD  AMOUNT  DESCRIPTION
e.g.  '05/20 2,029.54 DirectDeposit - ACH'

Lines that must NOT be treated as transactions:
  - the Balance Summary row (4 numbers: beginning/deposits/deductions/ending)
  - the daily-balance ledger near the end (repeated 'MM/DD amount' pairs)
"""
import re
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import date

from src.models import Transaction, TransactionType, ProcessingResult
from src.parsers.base_parser import BaseParser


class PNCParser(BaseParser):
    """Parser for PNC Bank Virtual Wallet statement PDFs."""

    INSTITUTION = "pnc"
    SUPPORTED_FORMATS = ["pdf"]

    # Section headers (matched as substrings against a normalized line).
    CREDIT_SECTION_MARKERS = [
        "deposits and other additions",
    ]
    DEBIT_SECTION_MARKERS = [
        "banking/debit card withdrawals",
        "banking/debitcardwithdrawals",
        "online and electronic banking deductions",
        "onlineand electronicbankingdeductions",
        "checks and substitute checks",
    ]
    # Section headers that end transaction parsing for a block (balance ledger etc.)
    STOP_SECTION_MARKERS = [
        "daily balance detail",
        "daily balance",
    ]

    # A transaction row: MM/DD  <amount>  <description>
    TXN_RE = re.compile(r'^(\d{2}/\d{2})\s+([\d,]+\.\d{2})\s+(.+)$')

    def __init__(self, file_path: str, account_id: Optional[str] = None):
        super().__init__(file_path, account_id)
        self._pages: List[str] = []
        self._text_content: Optional[str] = None

    # ---------- text extraction ----------

    def _extract_text(self) -> bool:
        try:
            import pdfplumber
            pages = []
            with pdfplumber.open(str(self.file_path)) as pdf:
                for page in pdf.pages:
                    pages.append(page.extract_text() or "")
            self._pages = pages
            self._text_content = "\n".join(pages)
            return len(self._text_content.strip()) > 100
        except Exception as e:
            self.errors.append(f"PDF extraction failed: {e}")
            return False

    def _get_statement_year(self) -> Tuple[int, int]:
        """
        Return (start_year, end_year) from the 'For the period MM/DD/YYYY to
        MM/DD/YYYY' line so we can resolve MM/DD rows (statements can straddle
        a year boundary).
        """
        text = self._text_content or ""
        m = re.search(r'period\s+(\d{2})/(\d{2})/(\d{4})\s+to\s+(\d{2})/(\d{2})/(\d{4})', text, re.I)
        if m:
            return int(m.group(3)), int(m.group(6))
        from datetime import datetime
        y = datetime.now().year
        return y, y

    def _resolve_date(self, mmdd: str, start_year: int, end_year: int,
                      start_month: int) -> Optional[date]:
        """Resolve a MM/DD string to a full date using the statement period."""
        try:
            month, day = int(mmdd[:2]), int(mmdd[3:5])
        except (ValueError, IndexError):
            return None
        # If the statement crosses a year boundary (e.g. Dec->Jan), rows with a
        # month earlier than the start month belong to the end year.
        year = start_year
        if end_year != start_year and month < start_month:
            year = end_year
        try:
            return date(year, month, day)
        except ValueError:
            return None

    # ---------- line classification ----------

    @staticmethod
    def _normalize(line: str) -> str:
        return re.sub(r'\s+', ' ', line).strip().lower()

    def _is_balance_summary_row(self, line: str) -> bool:
        """
        The Balance Summary row is 3-4 bare amounts with no description, e.g.
        '11,928.84 12,069.70 5,604.42 18,394.12'. Reject it.
        """
        tokens = line.split()
        if len(tokens) < 3:
            return False
        amount_like = all(re.fullmatch(r'[\d,]+\.\d{2}', t) for t in tokens)
        return amount_like

    def _is_daily_balance_row(self, line: str) -> bool:
        """
        Daily balance ledger rows repeat 'MM/DD amount' pairs, e.g.
        '05/14 3,837.56 05/27 7,481.25 06/03 8,723.16 06/11 8,419.18'.
        They contain 2+ date tokens on one line.
        """
        dates = re.findall(r'\d{2}/\d{2}', line)
        return len(dates) >= 2

    # ---------- parsing ----------

    def parse_pdf(self) -> ProcessingResult:
        if not self._extract_text():
            return ProcessingResult(
                file_path=str(self.file_path), file_type="pdf",
                institution=self.INSTITUTION, account_type="checking",
                success=False, errors=self.errors or ["Could not extract text from PDF"],
            )

        start_year, end_year = self._get_statement_year()
        # start month from the period line, for year-boundary resolution
        m = re.search(r'period\s+(\d{2})/', self._text_content or "")
        start_month = int(m.group(1)) if m else 1

        transactions: List[Transaction] = []
        current_type: Optional[TransactionType] = None

        for page_text in self._pages:
            for raw in page_text.split('\n'):
                line = raw.strip()
                if not line:
                    continue

                norm = self._normalize(line)

                # Section transitions
                if any(mark in norm for mark in self.STOP_SECTION_MARKERS):
                    current_type = None
                    continue
                if any(mark in norm for mark in self.CREDIT_SECTION_MARKERS):
                    current_type = TransactionType.CREDIT
                    continue
                if any(mark in norm for mark in self.DEBIT_SECTION_MARKERS):
                    current_type = TransactionType.DEBIT
                    continue

                # Only parse rows while inside a known section
                if current_type is None:
                    continue

                # Skip non-transaction noise
                if self._is_daily_balance_row(line):
                    continue
                if self._is_balance_summary_row(line):
                    continue

                match = self.TXN_RE.match(line)
                if not match:
                    continue

                mmdd, amount_str, desc = match.groups()
                # A row whose "description" is itself just numbers is a ledger line
                if self._is_balance_summary_row(f"{amount_str} {desc}"):
                    continue

                tx_date = self._resolve_date(mmdd, start_year, end_year, start_month)
                if not tx_date:
                    continue

                try:
                    amount = float(amount_str.replace(',', ''))
                except ValueError:
                    continue
                if amount == 0:
                    continue

                description = self._clean_description(desc)

                tx = Transaction(
                    id=self._generate_transaction_id(tx_date, description, amount),
                    date=tx_date,
                    description=description,
                    amount=amount,
                    transaction_type=current_type,
                    account_id=self.account_id or "pnc_checking",
                    institution=self.INSTITUTION,
                    original_description=desc.strip(),
                    source_file=str(self.file_path),
                    source_type="pdf",
                )
                transactions.append(tx)

        return ProcessingResult(
            file_path=str(self.file_path), file_type="pdf",
            institution=self.INSTITUTION, account_type="checking",
            success=len(transactions) > 0, transactions=transactions,
            warnings=self.warnings,
        )

    def parse_csv(self) -> ProcessingResult:
        return ProcessingResult(
            file_path=str(self.file_path), file_type="csv",
            institution=self.INSTITUTION, account_type="checking",
            success=False, errors=["PNC parser only supports PDF statements"],
        )

    @classmethod
    def can_handle(cls, file_path: str) -> Tuple[bool, float]:
        path = Path(file_path)
        if path.suffix.lower() != '.pdf':
            return False, 0.0

        # Filename hint
        if 'pnc' in path.stem.lower():
            return True, 0.9

        try:
            import pdfplumber
            with pdfplumber.open(str(file_path)) as pdf:
                if not pdf.pages:
                    return False, 0.0
                text = (pdf.pages[0].extract_text() or "").upper()
                # Strong, PNC-specific signatures
                if 'PNC BANK' in text:
                    return True, 0.97
                if 'VIRTUAL WALLET' in text and 'PNC' in text:
                    return True, 0.95
        except Exception:
            pass

        return False, 0.0
