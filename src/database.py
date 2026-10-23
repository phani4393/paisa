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
        
        # Accounts
        cursor.execute("SELECT DISTINCT account_id, institution FROM transactions")
        accounts = [{"id": row[0], "institution": row[1]} for row in cursor.fetchall()]
        
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
        
        params.append(limit)
        
        cursor.execute(f"""
            SELECT description, SUM(amount) as total, COUNT(*) as count
            FROM transactions 
            WHERE transaction_type = 'debit' {date_filter}
            GROUP BY description ORDER BY total DESC LIMIT ?
        """, params)
        
        merchants = [{"name": row[0], "amount": row[1], "count": row[2]} for row in cursor.fetchall()]
        conn.close()
        
        return merchants
