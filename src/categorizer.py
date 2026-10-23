"""
Rule-based transaction categorizer.
"""
from typing import Optional, Tuple
from src.models import Transaction
from src.database import Database


class Categorizer:
    """Categorizes transactions using pattern-matching rules."""
    
    def __init__(self, db: Database):
        self.db = db
        self._rules = None
        self._refresh_rules()
    
    def _refresh_rules(self):
        """Load rules from database."""
        self._rules = self.db.get_rules()
    
    def categorize(self, transaction: Transaction) -> Tuple[str, Optional[int]]:
        """
        Categorize a transaction.
        Returns (category, rule_id) or ("Uncategorized", None).
        """
        # Check description and original_description
        texts_to_check = [
            transaction.description.upper(),
            transaction.original_description.upper(),
            transaction.merchant_name.upper()
        ]
        
        for rule in self._rules:
            pattern = rule.pattern.upper()
            for text in texts_to_check:
                if pattern in text:
                    return rule.category, rule.id
        
        return "Uncategorized", None
    
    def categorize_transaction(self, transaction: Transaction) -> Transaction:
        """
        Categorize a transaction and update its category field.
        Also increments rule match count.
        """
        if transaction.user_categorized:
            # Don't override user categorization
            return transaction
        
        category, rule_id = self.categorize(transaction)
        transaction.category = category
        
        if rule_id:
            self.db.increment_rule_match(rule_id)
        
        return transaction
    
    def categorize_all(self, transactions: list) -> list:
        """Categorize a list of transactions."""
        return [self.categorize_transaction(tx) for tx in transactions]
    
    def add_rule(self, pattern: str, category: str) -> bool:
        """
        Add a new rule and refresh cache.
        Returns True if successful.
        """
        rule_id = self.db.add_rule(pattern, category)
        if rule_id:
            self._refresh_rules()
            return True
        return False
    
    def apply_rule_to_existing(self, pattern: str, category: str) -> int:
        """
        Apply a new rule to all existing transactions that match.
        Returns count of updated transactions.
        """
        transactions = self.db.get_transactions(uncategorized_only=True, limit=10000)
        pattern_upper = pattern.upper()
        updated = 0
        
        for tx in transactions:
            if pattern_upper in tx.description.upper() or pattern_upper in tx.original_description.upper():
                if self.db.update_transaction_category(tx.id, category):
                    updated += 1
        
        return updated
    
    def suggest_rule(self, transaction: Transaction) -> Optional[str]:
        """
        Suggest a rule pattern for a transaction.
        Returns a suggested pattern or None.
        """
        desc = transaction.original_description or transaction.description
        desc_upper = desc.upper()
        
        # Common prefixes to remove
        prefixes = [
            "CHECKCARD ", "DEBIT CARD ", "POS ", "PURCHASE ",
            "ACH ", "ELECTRONIC ", "RECURRING ", "AUTOMATIC "
        ]
        
        clean = desc_upper
        for prefix in prefixes:
            if clean.startswith(prefix):
                clean = clean[len(prefix):]
        
        # Get first meaningful word/phrase
        words = clean.split()
        if words:
            # Try to get a good identifier (2-3 words or first word if unique enough)
            if len(words) >= 2:
                # Check if second word is a number/date - if so, just use first
                if words[1].isdigit() or '/' in words[1]:
                    return words[0]
                return f"{words[0]} {words[1]}"
            return words[0]
        
        return None
