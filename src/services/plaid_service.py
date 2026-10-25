"""
Plaid API Service for Paisa

Handles all Plaid API interactions:
- Link token creation for Plaid Link widget
- Public token exchange for access tokens
- Transaction synchronization
"""

import os
from datetime import date, datetime, timedelta
from typing import Optional
from dataclasses import dataclass

import plaid
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
from plaid.model.products import Products
from plaid.model.country_code import CountryCode

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class LinkedAccount:
    """Represents a bank account linked via Plaid"""
    item_id: str
    access_token: str
    institution_id: str
    institution_name: str
    account_id: str
    account_name: str
    account_type: str
    account_mask: str  # Last 4 digits
    linked_at: datetime


@dataclass
class PlaidTransaction:
    """Raw transaction data from Plaid before conversion"""
    transaction_id: str
    account_id: str
    amount: float
    date: date
    name: str
    merchant_name: Optional[str]
    category: list[str]
    pending: bool
    payment_channel: str  # online, in store, other


class PlaidService:
    """
    Service class for Plaid API integration.
    
    Handles link token creation, token exchange, and transaction fetching.
    Converts Plaid transactions to Paisa's Transaction model format.
    """
    
    def __init__(
        self,
        client_id: Optional[str] = None,
        secret: Optional[str] = None,
        environment: Optional[str] = None
    ):
        """
        Initialize Plaid client.
        
        Args:
            client_id: Plaid client ID (defaults to PLAID_CLIENT_ID env var)
            secret: Plaid secret key (defaults to PLAID_SECRET env var)
            environment: 'sandbox', 'development', or 'production'
                (defaults to the PLAID_ENV env var, then 'sandbox').
                NOTE: must default to None here, not "sandbox" — otherwise the
                truthy default would always win over PLAID_ENV and silently send
                production keys to the sandbox host (=> INVALID_API_KEYS).
        """
        self.client_id = client_id or os.getenv("PLAID_CLIENT_ID")
        self.secret = secret or os.getenv("PLAID_SECRET")
        self.environment = environment or os.getenv("PLAID_ENV", "sandbox")
        
        if not self.client_id or not self.secret:
            raise ValueError(
                "Plaid credentials required. Set PLAID_CLIENT_ID and PLAID_SECRET "
                "environment variables or pass them to the constructor."
            )
        
        # Configure Plaid client
        self.configuration = plaid.Configuration(
            host=self._get_host(),
            api_key={
                "clientId": self.client_id,
                "secret": self.secret,
            }
        )
        
        self.api_client = plaid.ApiClient(self.configuration)
        self.client = plaid_api.PlaidApi(self.api_client)
    
    def _get_host(self) -> str:
        """Get Plaid API host based on environment."""
        hosts = {
            "sandbox": plaid.Environment.Sandbox,
            "development": plaid.Environment.Development,
            "production": plaid.Environment.Production,
        }
        return hosts.get(self.environment.lower(), plaid.Environment.Sandbox)
    
    def create_link_token(self, user_id: str) -> dict:
        """
        Create a link token for Plaid Link widget.
        
        This token is used by the frontend to initialize Plaid Link,
        which lets users securely connect their bank accounts.
        
        Args:
            user_id: Unique identifier for the user in your system
            
        Returns:
            dict with 'link_token' and 'expiration' keys
        """
        required, optional = self._get_products()

        kwargs = dict(
            user=LinkTokenCreateRequestUser(client_user_id=user_id),
            client_name="Paisa Finance Tracker",
            products=[Products(p) for p in required],
            country_codes=[CountryCode("US")],
            language="en",
        )
        # 'additional_consented_products' tells Plaid to also pull these when the
        # bank supports them, WITHOUT making them required. This avoids the
        # "No liability accounts / connect a different bank" rejection for banks
        # that only have deposit accounts.
        if optional:
            kwargs["additional_consented_products"] = [Products(p) for p in optional]

        request = LinkTokenCreateRequest(**kwargs)

        response = self.client.link_token_create(request)
        
        return {
            "link_token": response.link_token,
            "expiration": response.expiration,
        }
    
    def _get_products(self) -> tuple:
        """
        Split configured products into (required, optional).

        'transactions' is always REQUIRED (every bank supports it). Everything
        else from PLAID_PRODUCTS (e.g. 'liabilities', 'investments') is treated
        as OPTIONAL / additional-consented, so a bank that lacks a mortgage or
        brokerage account can still be connected for its transactions.

        PLAID_PRODUCTS example: "transactions,liabilities,investments".
        Returns ( ["transactions"], ["liabilities", "investments"] ).
        """
        raw = os.getenv("PLAID_PRODUCTS", "transactions")
        configured = [p.strip() for p in raw.split(",") if p.strip()]

        required = ["transactions"]
        optional = [p for p in configured if p not in ("transactions",)]
        return required, optional
    
    def exchange_public_token(self, public_token: str) -> dict:
        """
        Exchange a public token for an access token.
        
        After a user successfully connects their bank via Plaid Link,
        you receive a public_token that must be exchanged for a
        permanent access_token.
        
        Args:
            public_token: Temporary token from Plaid Link success callback
            
        Returns:
            dict with 'access_token' and 'item_id' keys
        """
        request = ItemPublicTokenExchangeRequest(public_token=public_token)
        response = self.client.item_public_token_exchange(request)
        
        return {
            "access_token": response.access_token,
            "item_id": response.item_id,
        }
    
    def get_transactions(
        self,
        access_token: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        account_ids: Optional[list[str]] = None,
    ) -> list[PlaidTransaction]:
        """
        Fetch transactions from Plaid.
        
        Args:
            access_token: Permanent access token for the linked account
            start_date: Start of date range (defaults to 30 days ago)
            end_date: End of date range (defaults to today)
            account_ids: Optional list of specific account IDs to fetch
            
        Returns:
            List of PlaidTransaction objects
        """
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=30)
        
        # Plaid paginates results, so we fetch all pages using an offset.
        transactions: list[PlaidTransaction] = []
        total_transactions = None

        while True:
            options = TransactionsGetRequestOptions(offset=len(transactions))
            if account_ids:
                options.account_ids = account_ids

            request = TransactionsGetRequest(
                access_token=access_token,
                start_date=start_date,
                end_date=end_date,
                options=options,
            )

            response = self.client.transactions_get(request)

            if total_transactions is None:
                total_transactions = response.total_transactions

            for txn in response.transactions:
                transactions.append(PlaidTransaction(
                    transaction_id=txn.transaction_id,
                    account_id=txn.account_id,
                    amount=float(txn.amount),
                    date=txn.date,
                    name=txn.name,
                    merchant_name=txn.merchant_name,
                    category=txn.category or [],
                    pending=txn.pending,
                    payment_channel=txn.payment_channel,
                ))

            # Stop when we've collected everything (or got an empty page)
            if not response.transactions or len(transactions) >= total_transactions:
                break

        return transactions
    
    def get_accounts(self, access_token: str) -> list[dict]:
        """
        Get account information for a linked item.
        
        Args:
            access_token: Permanent access token for the linked item
            
        Returns:
            List of account dictionaries with id, name, type, subtype, mask
        """
        from plaid.model.accounts_get_request import AccountsGetRequest
        
        request = AccountsGetRequest(access_token=access_token)
        response = self.client.accounts_get(request)
        
        accounts = []
        for account in response.accounts:
            accounts.append({
                "account_id": account.account_id,
                "name": account.name,
                "official_name": account.official_name,
                "type": str(account.type),
                "subtype": str(account.subtype) if account.subtype else None,
                "mask": account.mask,
                "current_balance": float(account.balances.current) if account.balances.current else 0,
                "available_balance": float(account.balances.available) if account.balances.available else None,
            })
        
        return accounts
    
    def get_institution(self, access_token: str) -> dict:
        """
        Get institution information for a linked item.
        
        Args:
            access_token: Permanent access token for the linked item
            
        Returns:
            dict with institution_id and institution_name
        """
        from plaid.model.item_get_request import ItemGetRequest
        from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest
        
        # First get the item to find institution_id
        item_request = ItemGetRequest(access_token=access_token)
        item_response = self.client.item_get(item_request)
        institution_id = item_response.item.institution_id
        
        # Then get institution details
        inst_request = InstitutionsGetByIdRequest(
            institution_id=institution_id,
            country_codes=[CountryCode("US")],
        )
        inst_response = self.client.institutions_get_by_id(inst_request)
        
        return {
            "institution_id": institution_id,
            "institution_name": inst_response.institution.name,
        }
    
    def get_liabilities(self, access_token: str) -> dict:
        """
        Fetch liability details (mortgage, student loan, credit) for an item.

        Requires the 'liabilities' product to be enabled on your Plaid account
        and requested at link time (PLAID_PRODUCTS). Returns a normalized dict;
        mortgages do NOT have a transaction feed here - this is balance / rate /
        payment metadata. Raises if the product is not available.
        """
        from plaid.model.liabilities_get_request import LiabilitiesGetRequest

        request = LiabilitiesGetRequest(access_token=access_token)
        response = self.client.liabilities_get(request)
        liabilities = response.liabilities

        result = {"mortgage": [], "student": [], "credit": []}

        for m in (liabilities.mortgage or []):
            result["mortgage"].append({
                "account_id": m.account_id,
                "name": getattr(m, "property_address", None) and "Mortgage" or "Mortgage",
                "next_payment_due_date": str(getattr(m, "next_payment_due_date", "") or ""),
                "next_monthly_payment": float(getattr(m, "next_monthly_payment", 0) or 0),
                "interest_rate_pct": float(getattr(getattr(m, "interest_rate", None), "percentage", 0) or 0),
                "outstanding_balance": None,  # balance comes from accounts_get
            })
        for s in (getattr(liabilities, "student", None) or []):
            result["student"].append({
                "account_id": s.account_id,
                "outstanding_balance": float(getattr(s, "outstanding_interest_amount", 0) or 0),
            })
        for cr in (getattr(liabilities, "credit", None) or []):
            result["credit"].append({
                "account_id": cr.account_id,
                "last_payment_amount": float(getattr(cr, "last_payment_amount", 0) or 0),
            })

        return result
    
    def get_investment_transactions(
        self,
        access_token: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list:
        """
        Fetch investment transactions (buys, sells, dividends) for an item.

        Requires the 'investments' product enabled + requested at link time.
        Returns a list of normalized dicts. Raises if not available.
        """
        from plaid.model.investments_transactions_get_request import (
            InvestmentsTransactionsGetRequest,
        )

        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = date(end_date.year, 1, 1)

        request = InvestmentsTransactionsGetRequest(
            access_token=access_token,
            start_date=start_date,
            end_date=end_date,
        )
        response = self.client.investments_transactions_get(request)

        txns = []
        for it in response.investment_transactions:
            txns.append({
                "investment_transaction_id": it.investment_transaction_id,
                "account_id": it.account_id,
                "date": it.date,
                "name": it.name,
                "amount": float(it.amount),
                "type": str(it.type),
                "subtype": str(it.subtype) if it.subtype else None,
            })
        return txns


def convert_plaid_to_paisa(
    plaid_txn: PlaidTransaction,
    institution_name: str,
    account_name: str,
) -> dict:
    """
    Convert a Plaid transaction to Paisa Transaction format.
    
    Note: Returns a dict that can be passed to Transaction() constructor.
    The Transaction dataclass is imported in the calling code to avoid
    circular imports.
    
    Args:
        plaid_txn: PlaidTransaction from Plaid API
        institution_name: Name of the financial institution
        account_name: Name of the specific account
        
    Returns:
        dict compatible with Paisa's Transaction dataclass
    """
    from src.models import TransactionType
    
    # Plaid uses positive amounts for debits (money out) and negative for credits
    # Paisa expects positive amounts with transaction_type indicating direction
    amount = abs(plaid_txn.amount)
    
    # Determine transaction type
    # In Plaid: positive = money leaving account (debit), negative = money coming in (credit)
    if plaid_txn.amount > 0:
        txn_type = TransactionType.DEBIT
    else:
        txn_type = TransactionType.CREDIT
    
    # Use Plaid's merchant name if available, otherwise fall back to name
    merchant = plaid_txn.merchant_name or plaid_txn.name
    
    # Map Plaid category to a single category string
    category = plaid_txn.category[0] if plaid_txn.category else "Uncategorized"
    
    return {
        "id": plaid_txn.transaction_id,
        "date": plaid_txn.date,
        "description": plaid_txn.name,
        "amount": amount,
        "transaction_type": txn_type,
        "account_id": plaid_txn.account_id,
        "institution": institution_name,
        "category": category,
        "merchant_name": merchant,
        "is_pending": plaid_txn.pending,
        "source": "plaid",
    }
