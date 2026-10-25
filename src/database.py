"""
SQLite database for Paisa.
Stores transactions, rules, and settings.
"""
import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional, Dict, Any
import json

from src.models import Transaction, TransactionType, Rule, DEFAULT_RULES, DEFAULT_CATEGORIES


class Database:
    """SQLite database manager for Paisa."""
    
    def __init__(self, db_path: str = "data/paisa.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _get_conn(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self):
        """Initialize database schema."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # Transactions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                transaction_type TEXT NOT NULL,
                account_id TEXT NOT NULL,
                institution TEXT NOT NULL,
                category TEXT DEFAULT 'Uncategorized',
                merchant_name TEXT DEFAULT '',
                original_description TEXT DEFAULT '',
                is_transfer INTEGER DEFAULT 0,
                is_recurring INTEGER DEFAULT 0,
                source_file TEXT DEFAULT '',
                source_type TEXT DEFAULT '',
                user_categorized INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Rules table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                match_count INTEGER DEFAULT 0
            )
        """)
        
        # Categories table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                name TEXT PRIMARY KEY,
                icon TEXT NOT NULL,
                color TEXT NOT NULL
            )
        """)
        
        # Settings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        
        # Budgets table (monthly budget per category)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS budgets (
                category TEXT PRIMARY KEY,
                monthly_limit REAL NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Balance snapshots table (net worth over time)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS balance_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT NOT NULL,
                account_id TEXT NOT NULL,
                institution_name TEXT DEFAULT '',
                account_name TEXT DEFAULT '',
                account_type TEXT DEFAULT '',
                balance REAL NOT NULL,
                is_liability INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_date ON balance_snapshots(snapshot_date)")
        
        # Imported files table (file-level dedup)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS imported_files (
                content_hash TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                institution TEXT DEFAULT '',
                tx_count INTEGER DEFAULT 0,
                imported_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Linked accounts table (Plaid)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS linked_accounts (
                account_id TEXT PRIMARY KEY,
                item_id TEXT NOT NULL,
                access_token TEXT NOT NULL,
                institution_id TEXT DEFAULT '',
                institution_name TEXT DEFAULT '',
                account_name TEXT DEFAULT '',
                account_type TEXT DEFAULT '',
                account_mask TEXT DEFAULT '',
                cursor TEXT DEFAULT '',
                last_synced TEXT DEFAULT '',
                linked_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Indexes for faster queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions(account_id)")
        
        conn.commit()
        
        # Insert default categories if empty
        cursor.execute("SELECT COUNT(*) FROM categories")
        if cursor.fetchone()[0] == 0:
            for cat in DEFAULT_CATEGORIES:
                cursor.execute(
                    "INSERT OR IGNORE INTO categories (name, icon, color) VALUES (?, ?, ?)",
                    (cat["name"], cat["icon"], cat["color"])
                )
            conn.commit()
        
        # Insert default rules if empty
        cursor.execute("SELECT COUNT(*) FROM rules")
        if cursor.fetchone()[0] == 0:
            for pattern, category in DEFAULT_RULES:
                cursor.execute(
                    "INSERT OR IGNORE INTO rules (pattern, category) VALUES (?, ?)",
                    (pattern.upper(), category)
                )
            conn.commit()
        
        conn.close()
    
    # ==================== TRANSACTIONS ====================
    
    def save_transaction(self, tx: Transaction) -> bool:
        """Save or update a transaction."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO transactions 
                (id, date, description, amount, transaction_type, account_id, institution,
                 category, merchant_name, original_description, is_transfer, is_recurring,
                 source_file, source_type, user_categorized)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tx.id, tx.date.isoformat(), tx.description, tx.amount,
                tx.transaction_type.value, tx.account_id, tx.institution,
                tx.category, tx.merchant_name, tx.original_description,
                int(tx.is_transfer), int(tx.is_recurring),
                tx.source_file, tx.source_type, int(tx.user_categorized)
            ))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error saving transaction: {e}")
            return False
        finally:
            conn.close()
    
    def save_transactions(self, transactions: List[Transaction]) -> int:
        """Save multiple transactions. Returns count of saved."""
        saved = 0
        for tx in transactions:
            if self.save_transaction(tx):
                saved += 1
        return saved
    
    def get_transaction(self, tx_id: str) -> Optional[Transaction]:
        """Get a transaction by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return self._row_to_transaction(row)
        return None
    
    def get_transactions(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        category: Optional[str] = None,
        account_id: Optional[str] = None,
        min_amount: Optional[float] = None,
        max_amount: Optional[float] = None,
        search: Optional[str] = None,
        uncategorized_only: bool = False,
        limit: int = 1000,
        offset: int = 0
    ) -> List[Transaction]:
        """Get transactions with filters."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        query = "SELECT * FROM transactions WHERE 1=1"
        params = []
        
        if start_date:
            query += " AND date >= ?"
            params.append(start_date.isoformat())
        
        if end_date:
            query += " AND date <= ?"
            params.append(end_date.isoformat())
        
        if category:
            query += " AND category = ?"
            params.append(category)
        
        if account_id:
            query += " AND account_id = ?"
            params.append(account_id)
        
        if min_amount is not None:
            query += " AND amount >= ?"
            params.append(min_amount)
        
        if max_amount is not None:
            query += " AND amount <= ?"
            params.append(max_amount)
        
        if search:
            query += " AND (description LIKE ? OR merchant_name LIKE ? OR original_description LIKE ?)"
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern, search_pattern])
        
        if uncategorized_only:
            query += " AND category = 'Uncategorized'"
        
        query += " ORDER BY date DESC, created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_transaction(row) for row in rows]
    
    def get_uncategorized_transactions(self, limit: int = 50) -> List[Transaction]:
        """Get uncategorized transactions for review."""
        return self.get_transactions(uncategorized_only=True, limit=limit)
    
    def update_transaction_category(self, tx_id: str, category: str) -> bool:
        """Update a transaction's category."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "UPDATE transactions SET category = ?, user_categorized = 1 WHERE id = ?",
                (category, tx_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def _row_to_transaction(self, row: sqlite3.Row) -> Transaction:
        """Convert database row to Transaction object."""
        return Transaction(
            id=row["id"],
            date=date.fromisoformat(row["date"]),
            description=row["description"],
            amount=row["amount"],
            transaction_type=TransactionType(row["transaction_type"]),
            account_id=row["account_id"],
            institution=row["institution"],
            category=row["category"],
            merchant_name=row["merchant_name"] or "",
            original_description=row["original_description"] or "",
            is_transfer=bool(row["is_transfer"]),
            is_recurring=bool(row["is_recurring"]),
            source_file=row["source_file"] or "",
            source_type=row["source_type"] or "",
            user_categorized=bool(row["user_categorized"])
        )
    
    def transaction_exists(self, tx_id: str) -> bool:
        """Check if a transaction already exists."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM transactions WHERE id = ?", (tx_id,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists
    
    # ==================== RULES ====================
    
    def get_rules(self) -> List[Rule]:
        """Get all categorization rules."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM rules ORDER BY match_count DESC, created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        
        return [
            Rule(
                id=row["id"],
                pattern=row["pattern"],
                category=row["category"],
                created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
                match_count=row["match_count"]
            )
            for row in rows
        ]
    
    def add_rule(self, pattern: str, category: str) -> Optional[int]:
        """Add a new categorization rule."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "INSERT OR REPLACE INTO rules (pattern, category) VALUES (?, ?)",
                (pattern.upper(), category)
            )
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            print(f"Error adding rule: {e}")
            return None
        finally:
            conn.close()
    
    def delete_rule(self, rule_id: int) -> bool:
        """Delete a rule."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        try:
            cursor.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def increment_rule_match(self, rule_id: int):
        """Increment match count for a rule."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE rules SET match_count = match_count + 1 WHERE id = ?", (rule_id,))
        conn.commit()
        conn.close()
    
    # ==================== CATEGORIES ====================
    
    def get_categories(self) -> List[Dict[str, str]]:
        """Get all categories."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM categories ORDER BY name")
        rows = cursor.fetchall()
        conn.close()
        
        return [{"name": row["name"], "icon": row["icon"], "color": row["color"]} for row in rows]
    
    def add_category(self, name: str, icon: str, color: str) -> bool:
        """Add a new category."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "INSERT OR REPLACE INTO categories (name, icon, color) VALUES (?, ?, ?)",
                (name, icon, color)
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"Error adding category: {e}")
            return False
        finally:
            conn.close()
    
    # ==================== IMPORTED FILES (DEDUP) ====================
    
    def file_already_imported(self, content_hash: str) -> Optional[str]:
        """Return the original filename if a file with this content hash was already imported."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT filename FROM imported_files WHERE content_hash = ?", (content_hash,))
        row = cursor.fetchone()
        conn.close()
        return row["filename"] if row else None
    
    def record_imported_file(self, content_hash: str, filename: str, institution: str = "", tx_count: int = 0) -> bool:
        """Record that a file (by content hash) has been imported."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT OR IGNORE INTO imported_files (content_hash, filename, institution, tx_count) VALUES (?, ?, ?, ?)",
                (content_hash, filename, institution, tx_count)
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"Error recording imported file: {e}")
            return False
        finally:
            conn.close()
    
    # ==================== LINKED ACCOUNTS (PLAID) ====================
    
    def save_linked_account(
        self,
        account_id: str,
        item_id: str,
        access_token: str,
        institution_id: str = "",
        institution_name: str = "",
        account_name: str = "",
        account_type: str = "",
        account_mask: str = "",
    ) -> bool:
        """Save or update a Plaid-linked account."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO linked_accounts
                (account_id, item_id, access_token, institution_id, institution_name,
                 account_name, account_type, account_mask, cursor, last_synced, linked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?,
                    COALESCE((SELECT cursor FROM linked_accounts WHERE account_id = ?), ''),
                    COALESCE((SELECT last_synced FROM linked_accounts WHERE account_id = ?), ''),
                    COALESCE((SELECT linked_at FROM linked_accounts WHERE account_id = ?), CURRENT_TIMESTAMP))
            """, (
                account_id, item_id, access_token, institution_id, institution_name,
                account_name, account_type, account_mask,
                account_id, account_id, account_id
            ))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error saving linked account: {e}")
            return False
        finally:
            conn.close()
    
    def get_linked_accounts(self) -> List[Dict[str, Any]]:
        """Get all linked accounts (without exposing access tokens)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT account_id, item_id, institution_id, institution_name,
                   account_name, account_type, account_mask, last_synced, linked_at
            FROM linked_accounts ORDER BY institution_name, account_name
        """)
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_linked_account(self, account_id: str) -> Optional[Dict[str, Any]]:
        """Get a single linked account including its access token (for API calls)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM linked_accounts WHERE account_id = ?", (account_id,))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def get_linked_accounts_full(self) -> List[Dict[str, Any]]:
        """Get all linked accounts including access tokens (for sync operations)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM linked_accounts")
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def update_account_sync(self, account_id: str, cursor_token: str = "") -> bool:
        """Update the last_synced timestamp and sync cursor for an account."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "UPDATE linked_accounts SET last_synced = ?, cursor = ? WHERE account_id = ?",
                (datetime.now().isoformat(), cursor_token, account_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def delete_linked_account(self, account_id: str) -> bool:
        """Remove a linked account."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        try:
            cursor.execute("DELETE FROM linked_accounts WHERE account_id = ?", (account_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    # ==================== ANALYTICS ====================
    
    def get_summary(self, start_date: Optional[date] = None, end_date: Optional[date] = None) -> Dict[str, Any]:
        """Get summary statistics."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        date_filter = ""
        params = []
        
        if start_date:
            date_filter += " AND date >= ?"
            params.append(start_date.isoformat())
        if end_date:
            date_filter += " AND date <= ?"
            params.append(end_date.isoformat())
        
        # Total income
        cursor.execute(f"""
            SELECT COALESCE(SUM(amount), 0) FROM transactions 
            WHERE transaction_type = 'credit' AND category != 'Transfer' {date_filter}
        """, params)
        total_income = cursor.fetchone()[0]
        
        # Total expenses
        cursor.execute(f"""
            SELECT COALESCE(SUM(amount), 0) FROM transactions 
            WHERE transaction_type = 'debit' AND category != 'Transfer' {date_filter}
        """, params)
        total_expenses = cursor.fetchone()[0]
        
        # Transaction count
        cursor.execute(f"SELECT COUNT(*) FROM transactions WHERE 1=1 {date_filter}", params)
        transaction_count = cursor.fetchone()[0]
        
        # Uncategorized count
        cursor.execute(f"""
            SELECT COUNT(*) FROM transactions 
            WHERE category = 'Uncategorized' {date_filter}
        """, params)
        uncategorized_count = cursor.fetchone()[0]
        
        # Category breakdown
        cursor.execute(f"""
            SELECT category, SUM(amount) as total, COUNT(*) as count
            FROM transactions 
            WHERE transaction_type = 'debit' AND category != 'Transfer' {date_filter}
            GROUP BY category ORDER BY total DESC
        """, params)
        categories = [{"name": row[0], "amount": row[1], "count": row[2]} for row in cursor.fetchall()]
        
        # Transfers excluded in this window (shown so totals are self-explanatory)
        cursor.execute(f"""
            SELECT COALESCE(SUM(amount),0) FROM transactions
            WHERE category = 'Transfer' {date_filter}
        """, params)
        transfers_excluded = round(cursor.fetchone()[0], 2)
        
        # Accounts
        cursor.execute("SELECT DISTINCT account_id, institution FROM transactions")
        accounts = [{"id": row[0], "institution": row[1]} for row in cursor.fetchall()]
        
        # Per-category anomaly flags. These only make sense for a single-month
        # view (comparing that month vs the average of OTHER months). For
        # multi-month ranges a sum-vs-monthly-average comparison is meaningless,
        # so we skip it to avoid flagging everything.
        anomalies = []
        try:
            # Determine if the selected window is a single calendar month.
            single_month_ym = None
            if start_date and end_date and start_date.year == end_date.year and start_date.month == end_date.month:
                single_month_ym = f"{start_date.year:04d}-{start_date.month:02d}"

            if single_month_ym:
                cursor.execute("""
                    SELECT category, substr(date,1,7) AS ym, SUM(amount) AS tot
                    FROM transactions
                    WHERE transaction_type='debit' AND category != 'Transfer'
                    GROUP BY category, ym
                """)
                from collections import defaultdict
                by_cat_month = defaultdict(dict)
                for r in cursor.fetchall():
                    by_cat_month[r[0]][r[1]] = r[2]
                for cat in categories:
                    name = cat["name"]
                    months_map = by_cat_month.get(name, {})
                    this_month = months_map.get(single_month_ym, 0)
                    others = [v for k, v in months_map.items() if k != single_month_ym]
                    if len(others) >= 2 and this_month > 0:
                        avg = sum(others) / len(others)
                        if avg > 0 and this_month > avg * 1.75 and this_month - avg > 100:
                            anomalies.append({
                                "category": name,
                                "amount": round(this_month, 2),
                                "typical": round(avg, 2),
                                "ratio": round(this_month / avg, 1),
                            })
        except Exception:
            pass
        
        conn.close()
        
        net_cash_flow = total_income - total_expenses
        savings_rate = (net_cash_flow / total_income * 100) if total_income > 0 else 0
        
        return {
            "total_income": total_income,
            "total_expenses": total_expenses,
            "net_cash_flow": net_cash_flow,
            "savings_rate": round(savings_rate, 1),
            "transaction_count": transaction_count,
            "uncategorized_count": uncategorized_count,
            "transfers_excluded": transfers_excluded,
            "anomalies": anomalies,
            "categories": categories,
            "accounts": accounts
        }
    
    def get_top_merchants(self, limit: int = 10, start_date: Optional[date] = None, end_date: Optional[date] = None) -> List[Dict]:
        """Get top merchants by spending."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        date_filter = ""
        params = []
        
        if start_date:
            date_filter += " AND date >= ?"
            params.append(start_date.isoformat())
        if end_date:
            date_filter += " AND date <= ?"
            params.append(end_date.isoformat())
        
        # Pull raw debit rows (excluding Transfers), then normalize merchant
        # names in Python so store-number / city variants collapse together.
        cursor.execute(f"""
            SELECT description, merchant_name, amount
            FROM transactions
            WHERE transaction_type = 'debit' AND category != 'Transfer' {date_filter}
        """, params)
        rows = cursor.fetchall()
        conn.close()

        from collections import defaultdict
        agg = defaultdict(lambda: {"amount": 0.0, "count": 0})
        for row in rows:
            key = self._normalize_merchant(row["merchant_name"], row["description"])
            agg[key]["amount"] += row["amount"]
            agg[key]["count"] += 1

        merchants = [
            {"name": name, "amount": round(v["amount"], 2), "count": v["count"]}
            for name, v in agg.items()
        ]
        merchants.sort(key=lambda m: m["amount"], reverse=True)
        return merchants[:limit]

    @staticmethod
    def _normalize_merchant(merchant_name: str, description: str) -> str:
        """
        Produce a stable display name for grouping merchants.
        Prefer the Plaid/parser merchant_name; otherwise derive from description
        by stripping store numbers, city/state, phone and reference noise so
        'WAL-MART #3400 OSWEGO IL' and 'WAL-MART #4185 CUMMING GA' merge.
        """
        import re

        # Known aliases that should collapse to a single canonical name.
        ALIASES = {
            "WALMART": "Walmart", "WAL MART": "Walmart", "WALMART.COM": "Walmart",
            "WM SUPERCENTER": "Walmart", "WAL-MART": "Walmart",
            "AMAZON": "Amazon", "AMAZON MKTPL": "Amazon", "AMAZON MKTPLACE": "Amazon",
            "AMZN MKTP": "Amazon", "AMAZON RETA": "Amazon",
            "TEMU": "Temu", "TEMU.COM": "Temu",
            "COSTCO WHSE": "Costco", "COSTCO GAS": "Costco",
        }

        def clean(text: str) -> str:
            d = (text or "").strip().upper()
            if not d:
                return ""
            # strip leading reference prefixes like "*7168 " or "1234 "
            d = re.sub(r'^\*?\d{2,}\s+', '', d)
            # cut at store-number markers or long digit runs
            d = re.split(r'\s+#?\d{3,}', d)[0]
            # normalize punctuation: hyphens, dots, asterisks -> space
            d = re.sub(r'[\-\.\*]', ' ', d)
            d = d.replace(' COM', '')
            # remove trailing 2-letter state code
            d = re.sub(r'\s+[A-Z]{2}\b', ' ', d)
            # collapse a word immediately repeated (e.g. NAPERVILLENAPERVILLE)
            tokens = d.split()
            deduped = []
            for t in tokens:
                half = len(t) // 2
                if len(t) > 8 and t[:half] == t[half:]:
                    t = t[:half]
                if not deduped or deduped[-1] != t:
                    deduped.append(t)
            d = ' '.join(deduped).strip()

            # apply alias map: check progressively shorter prefixes
            words = d.split()
            for take in (3, 2, 1):
                prefix = ' '.join(words[:take])
                if prefix in ALIASES:
                    return ALIASES[prefix].upper()  # return upper; caller .title()s
            return ' '.join(words[:2])

        # Prefer the clean Plaid/parser merchant_name, but still normalize it so
        # it merges with description-derived rows for the same merchant.
        name = clean(merchant_name) or clean(description)
        return name.title() if name else "Unknown"
    
    def get_monthly_trend(self, months: int = 12) -> List[Dict[str, Any]]:
        """
        Income vs expenses per calendar month for the last `months` months.
        Transfers are excluded so the figures reflect real money in/out.
        Returns a list ordered oldest -> newest.
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT substr(date, 1, 7) AS ym,
                   COALESCE(SUM(CASE WHEN transaction_type='credit' AND category != 'Transfer' THEN amount ELSE 0 END), 0) AS income,
                   COALESCE(SUM(CASE WHEN transaction_type='debit'  AND category != 'Transfer' THEN amount ELSE 0 END), 0) AS expenses
            FROM transactions
            GROUP BY ym
            ORDER BY ym
        """)
        rows = cursor.fetchall()
        conn.close()
        
        result = []
        for row in rows:
            income = round(row["income"], 2)
            expenses = round(row["expenses"], 2)
            result.append({
                "month": row["ym"],                 # 'YYYY-MM'
                "income": income,
                "expenses": expenses,
                "net": round(income - expenses, 2),
            })
        
        # Keep only the most recent `months` buckets
        if months and len(result) > months:
            result = result[-months:]
        return result
    
    # ==================== NET WORTH / BALANCE SNAPSHOTS ====================
    
    # Account types/subtypes that represent money owed (liabilities).
    LIABILITY_HINTS = ("credit", "loan", "mortgage", "line of credit")
    
    def save_balance_snapshot(self, accounts: List[Dict[str, Any]], snapshot_date: Optional[str] = None) -> int:
        """
        Store a point-in-time balance snapshot for a set of accounts.
        `accounts` items: {account_id, institution_name, account_name,
        account_type, current_balance}. One snapshot per account per day
        (re-running same day overwrites that day's rows).
        Returns number of rows written.
        """
        from datetime import date as _date
        snap = snapshot_date or _date.today().isoformat()
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # clear existing rows for this date so a re-capture is idempotent
            cursor.execute("DELETE FROM balance_snapshots WHERE snapshot_date = ?", (snap,))
            n = 0
            for a in accounts:
                atype = (a.get("account_type") or "").lower()
                subtype = (a.get("subtype") or "").lower()
                is_liab = any(h in atype or h in subtype for h in self.LIABILITY_HINTS)
                bal = a.get("current_balance")
                if bal is None:
                    continue
                cursor.execute("""
                    INSERT INTO balance_snapshots
                    (snapshot_date, account_id, institution_name, account_name, account_type, balance, is_liability)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (snap, a.get("account_id", ""), a.get("institution_name", ""),
                      a.get("account_name", ""), a.get("account_type", ""),
                      float(bal), 1 if is_liab else 0))
                n += 1
            conn.commit()
            return n
        finally:
            conn.close()
    
    def get_net_worth_history(self) -> List[Dict[str, Any]]:
        """
        Net worth per snapshot date: assets (non-liability balances) minus
        liabilities. Returns oldest -> newest.
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT snapshot_date,
                   COALESCE(SUM(CASE WHEN is_liability=0 THEN balance ELSE 0 END), 0) AS assets,
                   COALESCE(SUM(CASE WHEN is_liability=1 THEN balance ELSE 0 END), 0) AS liabilities
            FROM balance_snapshots
            GROUP BY snapshot_date
            ORDER BY snapshot_date
        """)
        rows = cursor.fetchall()
        conn.close()
        result = []
        for r in rows:
            assets = round(r["assets"], 2)
            liabilities = round(r["liabilities"], 2)
            result.append({
                "date": r["snapshot_date"],
                "assets": assets,
                "liabilities": liabilities,
                "net_worth": round(assets - liabilities, 2),
            })
        return result
    
    # ==================== TRANSFER AUTO-DETECTION ====================
    
    def detect_transfers(self, day_window: int = 3, apply: bool = False) -> Dict[str, Any]:
        """
        Find likely inter-account transfers: a debit in one account that has a
        matching credit of the SAME amount in a DIFFERENT account within
        `day_window` days. Both legs are the user moving their own money, so
        both should be categorized 'Transfer'.

        Returns the matched pairs. If apply=True, updates both legs to Transfer
        (only touches rows not already Transfer).
        """
        from datetime import date as _date, timedelta as _td

        conn = self._get_conn()
        cursor = conn.cursor()

        # candidate legs not already marked Transfer
        cursor.execute("""
            SELECT id, date, amount, transaction_type, account_id, institution, category, description
            FROM transactions
            WHERE category != 'Transfer'
            ORDER BY date
        """)
        rows = [dict(r) for r in cursor.fetchall()]

        debits = [r for r in rows if r["transaction_type"] == "debit"]
        credits = [r for r in rows if r["transaction_type"] == "credit"]

        # index credits by rounded amount for quick lookup
        from collections import defaultdict
        credits_by_amt = defaultdict(list)
        for cr in credits:
            credits_by_amt[round(cr["amount"], 2)].append(cr)

        matched = []
        used_credit_ids = set()
        used_debit_ids = set()

        for d in debits:
            if d["id"] in used_debit_ids:
                continue
            amt = round(d["amount"], 2)
            try:
                d_date = _date.fromisoformat(d["date"])
            except ValueError:
                continue
            for cr in credits_by_amt.get(amt, []):
                if cr["id"] in used_credit_ids:
                    continue
                # must be a DIFFERENT account (own-account transfer)
                if cr["account_id"] == d["account_id"]:
                    continue
                try:
                    c_date = _date.fromisoformat(cr["date"])
                except ValueError:
                    continue
                if abs((c_date - d_date).days) <= day_window:
                    matched.append({
                        "amount": amt,
                        "debit": {"id": d["id"], "date": d["date"], "institution": d["institution"], "description": d["description"][:40]},
                        "credit": {"id": cr["id"], "date": cr["date"], "institution": cr["institution"], "description": cr["description"][:40]},
                    })
                    used_credit_ids.add(cr["id"])
                    used_debit_ids.add(d["id"])
                    break

        applied = 0
        if apply and matched:
            for m in matched:
                for leg in ("debit", "credit"):
                    cursor.execute(
                        "UPDATE transactions SET category='Transfer' WHERE id=? AND category!='Transfer'",
                        (m[leg]["id"],)
                    )
                    applied += cursor.rowcount
            conn.commit()

        conn.close()
        return {"matched_pairs": len(matched), "pairs": matched, "updated": applied}
    
    # ==================== RECURRING ====================
    
    def get_recurring(self, min_occurrences: int = 3, lookback_months: int = 6) -> List[Dict[str, Any]]:
        """
        Detect recurring charges (subscriptions, loans, bills).

        Heuristic: group debits by normalized merchant; a merchant is recurring
        if it appears in >= min_occurrences distinct months within the lookback
        window. Reports the typical (median) amount, cadence, last charge, and a
        price-change flag if the latest amount differs notably from the earliest.
        Transfers are excluded.
        """
        from datetime import date as _date
        from collections import defaultdict
        import statistics

        conn = self._get_conn()
        cursor = conn.cursor()

        # lookback cutoff
        today = _date.today()
        start_year = today.year
        start_month = today.month - (lookback_months - 1)
        while start_month <= 0:
            start_month += 12
            start_year -= 1
        cutoff = f"{start_year:04d}-{start_month:02d}"

        cursor.execute("""
            SELECT date, amount, description, merchant_name
            FROM transactions
            WHERE transaction_type='debit' AND category != 'Transfer'
              AND substr(date,1,7) >= ?
        """, (cutoff,))
        rows = cursor.fetchall()
        conn.close()

        groups = defaultdict(list)
        for r in rows:
            key = self._normalize_merchant(r["merchant_name"], r["description"])
            groups[key].append({"date": r["date"], "amount": round(r["amount"], 2)})

        recurring = []
        for merchant, txns in groups.items():
            months = {t["date"][:7] for t in txns}
            if len(months) < min_occurrences:
                continue

            txns.sort(key=lambda t: t["date"])
            amounts = [t["amount"] for t in txns]
            median_amt = round(statistics.median(amounts), 2)
            if median_amt <= 0:
                continue

            # A real recurring charge (bill/subscription/loan) has a roughly
            # FIXED amount. Use coefficient of variation to reject variable
            # same-merchant spend like groceries. Also cap occurrences-per-month:
            # a subscription hits ~once/month, not 10x.
            if len(amounts) > 1:
                try:
                    cv = statistics.pstdev(amounts) / median_amt
                except statistics.StatisticsError:
                    cv = 0
            else:
                cv = 0
            avg_per_month = len(txns) / max(1, len(months))
            if cv > 0.25:        # amounts too variable -> not a fixed recurring charge
                continue
            if avg_per_month > 1.6:  # too frequent -> a shopping habit, not a bill
                continue

            # cadence estimate from month count vs span
            first_amt = amounts[0]
            last_amt = amounts[-1]
            price_change = None
            if first_amt > 0 and abs(last_amt - first_amt) / first_amt >= 0.1:
                price_change = {
                    "from": first_amt,
                    "to": last_amt,
                    "direction": "up" if last_amt > first_amt else "down",
                }

            recurring.append({
                "merchant": merchant,
                "typical_amount": median_amt,
                "occurrences": len(txns),
                "months_seen": len(months),
                "last_date": txns[-1]["date"],
                "last_amount": last_amt,
                "price_change": price_change,
                "est_monthly": median_amt,  # assumes ~monthly cadence
            })

        recurring.sort(key=lambda x: x["typical_amount"], reverse=True)
        return recurring
    
    # ==================== BUDGETS ====================
    
    def set_budget(self, category: str, monthly_limit: float) -> bool:
        """Create or update the monthly budget for a category."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT OR REPLACE INTO budgets (category, monthly_limit) VALUES (?, ?)",
                (category, float(monthly_limit))
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"Error setting budget: {e}")
            return False
        finally:
            conn.close()
    
    def delete_budget(self, category: str) -> bool:
        """Remove a category budget."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM budgets WHERE category = ?", (category,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def get_budgets(self) -> List[Dict[str, Any]]:
        """Get all category budgets."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT category, monthly_limit FROM budgets ORDER BY category")
        rows = cursor.fetchall()
        conn.close()
        return [{"category": r["category"], "monthly_limit": r["monthly_limit"]} for r in rows]
    
    def get_budget_status(self, year: int, month: int) -> List[Dict[str, Any]]:
        """
        Budget vs actual spend for a given month.
        Returns one row per budgeted category with limit, spent, remaining, pct.
        Transfers are never budgeted. Spend = debits in that category/month.
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        ym = f"{year:04d}-{month:02d}"
        cursor.execute("SELECT category, monthly_limit FROM budgets ORDER BY category")
        budgets = cursor.fetchall()
        
        status = []
        for b in budgets:
            cat = b["category"]
            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) FROM transactions
                WHERE transaction_type='debit' AND category = ?
                  AND substr(date,1,7) = ?
            """, (cat, ym))
            spent = round(cursor.fetchone()[0], 2)
            limit = round(b["monthly_limit"], 2)
            remaining = round(limit - spent, 2)
            pct = round((spent / limit * 100), 1) if limit > 0 else 0
            status.append({
                "category": cat,
                "monthly_limit": limit,
                "spent": spent,
                "remaining": remaining,
                "pct_used": pct,
                "over_budget": spent > limit,
            })
        
        conn.close()
        return status
