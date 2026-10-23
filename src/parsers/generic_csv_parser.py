"""
Generic CSV Parser that handles common bank CSV formats.
"""
from pathlib import Path
from typing import List, Optional, Tuple
import csv
from datetime import date

from src.models import Transaction, TransactionType, ProcessingResult
from src.parsers.base_parser import BaseParser


class GenericCSVParser(BaseParser):
    """Generic parser for CSV files with common formats."""
    
    INSTITUTION = "generic"
    SUPPORTED_FORMATS = ["csv"]
    
    # Common column name variations
    DATE_COLUMNS = ['date', 'transaction date', 'post date', 'posting date', 'trans date', 'trans_date']
    DESC_COLUMNS = ['description', 'desc', 'merchant', 'name', 'payee', 'memo', 'details', 'narrative']
    AMOUNT_COLUMNS = ['amount', 'amt', 'value', 'sum', 'total']
    DEBIT_COLUMNS = ['debit', 'withdrawal', 'withdrawals', 'payment', 'spend']
    CREDIT_COLUMNS = ['credit', 'deposit', 'deposits', 'income']
    
    def __init__(self, file_path: str, account_id: Optional[str] = None):
        super().__init__(file_path, account_id)
        self.detected_format = None
    
    def _detect_columns(self, headers: List[str]) -> dict:
        """Detect which columns contain which data."""
        headers_lower = [h.lower().strip() for h in headers]
        
        detected = {
            'date': None,
            'description': None,
            'amount': None,
            'debit': None,
            'credit': None,
            'type': None
        }
        
        for i, header in enumerate(headers_lower):
            # Date column
            if detected['date'] is None:
                for col in self.DATE_COLUMNS:
                    if col in header:
                        detected['date'] = i
                        break
            
            # Description column
            if detected['description'] is None:
                for col in self.DESC_COLUMNS:
                    if col in header:
                        detected['description'] = i
                        break
            
            # Amount column (single column with sign)
            if detected['amount'] is None:
                for col in self.AMOUNT_COLUMNS:
                    if col == header or header.startswith(col):
                        detected['amount'] = i
                        break
            
            # Separate debit/credit columns
            if detected['debit'] is None:
                for col in self.DEBIT_COLUMNS:
                    if col in header:
                        detected['debit'] = i
                        break
            
            if detected['credit'] is None:
                for col in self.CREDIT_COLUMNS:
                    if col in header:
                        detected['credit'] = i
                        break
            
            # Transaction type column
            if 'type' in header or 'trans type' in header:
                detected['type'] = i
        
        return detected
    
    def parse_csv(self) -> ProcessingResult:
        """Parse generic CSV file."""
        transactions = []
        
        try:
            with open(self.file_path, 'r', encoding='utf-8-sig') as f:
                # Try to detect delimiter
                sample = f.read(2048)
                f.seek(0)
                
                dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
                reader = csv.reader(f, dialect)
                
                # Get headers
                headers = next(reader)
                columns = self._detect_columns(headers)
                
                if columns['date'] is None:
                    return ProcessingResult(
                        file_path=str(self.file_path),
                        file_type="csv",
                        institution=self.INSTITUTION,
                        account_type="unknown",
                        success=False,
                        errors=["Could not detect date column in CSV"]
                    )
                
                if columns['description'] is None:
                    return ProcessingResult(
                        file_path=str(self.file_path),
                        file_type="csv",
                        institution=self.INSTITUTION,
                        account_type="unknown",
                        success=False,
                        errors=["Could not detect description column in CSV"]
                    )
                
                if columns['amount'] is None and columns['debit'] is None:
                    return ProcessingResult(
                        file_path=str(self.file_path),
                        file_type="csv",
                        institution=self.INSTITUTION,
                        account_type="unknown",
                        success=False,
                        errors=["Could not detect amount column in CSV"]
                    )
                
                # Parse rows
                for row_num, row in enumerate(reader, start=2):
                    if not row or all(not cell.strip() for cell in row):
                        continue
                    
                    try:
                        # Get date
                        date_str = row[columns['date']].strip()
                        tx_date = self._parse_date(date_str)
                        if not tx_date:
                            continue
                        
                        # Get description
                        desc = row[columns['description']].strip()
                        if not desc:
                            continue
                        
                        # Get amount
                        if columns['amount'] is not None:
                            amount_str = row[columns['amount']].strip()
                            if not amount_str:
                                continue
                            amount, tx_type = self._parse_amount(amount_str)
                        elif columns['debit'] is not None or columns['credit'] is not None:
                            # Separate debit/credit columns
                            debit_str = row[columns['debit']].strip() if columns['debit'] else ""
                            credit_str = row[columns['credit']].strip() if columns['credit'] else ""
                            
                            if debit_str and debit_str not in ['', '0', '0.00']:
                                amount, _ = self._parse_amount(debit_str)
                                tx_type = TransactionType.DEBIT
                            elif credit_str and credit_str not in ['', '0', '0.00']:
                                amount, _ = self._parse_amount(credit_str)
                                tx_type = TransactionType.CREDIT
                            else:
                                continue
                        else:
                            continue
                        
                        if amount == 0:
                            continue
                        
                        # Create transaction
                        tx = Transaction(
                            id=self._generate_transaction_id(tx_date, desc, amount),
                            date=tx_date,
                            description=self._clean_description(desc),
                            amount=amount,
                            transaction_type=tx_type,
                            account_id=self.account_id,
                            institution=self.INSTITUTION,
                            original_description=desc,
                            source_file=str(self.file_path),
                            source_type="csv"
                        )
                        transactions.append(tx)
                        
                    except Exception as e:
                        self.warnings.append(f"Row {row_num}: {str(e)}")
                
        except Exception as e:
            return ProcessingResult(
                file_path=str(self.file_path),
                file_type="csv",
                institution=self.INSTITUTION,
                account_type="unknown",
                success=False,
                errors=[f"CSV parsing error: {str(e)}"]
            )
        
        return ProcessingResult(
            file_path=str(self.file_path),
            file_type="csv",
            institution=self.INSTITUTION,
            account_type="unknown",
            success=len(transactions) > 0,
            transactions=transactions,
            warnings=self.warnings
        )
    
    def parse_pdf(self) -> ProcessingResult:
        """Not supported for generic CSV parser."""
        return ProcessingResult(
            file_path=str(self.file_path),
            file_type="pdf",
            institution=self.INSTITUTION,
            account_type="unknown",
            success=False,
            errors=["Generic CSV parser cannot handle PDF files"]
        )
    
    @classmethod
    def can_handle(cls, file_path: str) -> Tuple[bool, float]:
        """Check if this is a CSV file we can handle."""
        path = Path(file_path)
        
        if path.suffix.lower() != '.csv':
            return False, 0.0
        
        # Try to read and detect columns
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                sample = f.read(2048)
                f.seek(0)
                
                dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
                reader = csv.reader(f, dialect)
                headers = next(reader)
                
                parser = cls(file_path)
                columns = parser._detect_columns(headers)
                
                # Must have at least date and description
                if columns['date'] is not None and columns['description'] is not None:
                    # Must have some amount column
                    if columns['amount'] is not None or columns['debit'] is not None:
                        return True, 0.5  # Low confidence - it's generic
        except:
            pass
        
        return False, 0.0
