"""
Flask web application for Paisa.
"""
import os
import hashlib
from pathlib import Path
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

from src.database import Database
from src.categorizer import Categorizer
from src.parsers.parser_factory import ParserFactory
from src.models import Transaction


# Initialize Flask app
app = Flask(__name__, 
            template_folder='../templates',
            static_folder='../static')

# Configuration
app.config['UPLOAD_FOLDER'] = 'data/uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max
app.config['ALLOWED_EXTENSIONS'] = {'csv', 'pdf', 'xlsx', 'xls'}

# Ensure upload folder exists
Path(app.config['UPLOAD_FOLDER']).mkdir(parents=True, exist_ok=True)

# Initialize database and categorizer
db = Database()
categorizer = Categorizer(db)

# Initialize Plaid service lazily (only if credentials are configured)
_plaid_service = None


def get_plaid_service():
    """Get or create the Plaid service. Returns None if not configured.

    The plaid package and plaid_service module are imported lazily here so the
    app runs fine even when plaid-python is not installed. If the package is
    missing or credentials are not set, Plaid features are simply disabled.
    """
    global _plaid_service
    if _plaid_service is None:
        try:
            from src.services.plaid_service import PlaidService
            _plaid_service = PlaidService()
        except (ValueError, ImportError):
            # plaid not installed or credentials not configured
            return None
    return _plaid_service


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


# ==================== PAGES ====================

@app.route('/')
def index():
    """Main page."""
    return render_template('index.html')


# ==================== API: FILE UPLOAD ====================

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Handle file upload and parsing."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({
            'success': False, 
            'error': f'File type not supported. Allowed: {", ".join(app.config["ALLOWED_EXTENSIONS"])}'
        }), 400
    
    # Read content once so we can hash it for duplicate detection
    file_bytes = file.read()
    content_hash = hashlib.sha256(file_bytes).hexdigest()

    # If this exact file was already imported, skip re-processing it
    already = db.file_already_imported(content_hash)
    if already:
        return jsonify({
            'success': True,
            'message': f'This statement was already imported (as "{already}"). Skipped.',
            'new_count': 0,
            'duplicate_count': 0,
            'total_parsed': 0,
            'duplicate_file': True
        })

    # Save file
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_filename = f"{timestamp}_{filename}"
    file_path = Path(app.config['UPLOAD_FOLDER']) / unique_filename
    with open(str(file_path), 'wb') as out:
        out.write(file_bytes)
    
    # Parse file
    result = ParserFactory.parse_file(str(file_path))
    
    if not result.success:
        return jsonify({
            'success': False,
            'error': result.errors[0] if result.errors else 'Failed to parse file',
            'warnings': result.warnings
        }), 400
    
    # Categorize transactions
    transactions = categorizer.categorize_all(result.transactions)
    
    # Save to database
    new_count = 0
    duplicate_count = 0
    
    for tx in transactions:
        if not db.transaction_exists(tx.id):
            db.save_transaction(tx)
            new_count += 1
        else:
            duplicate_count += 1
    
    # Record this file's hash so an identical re-upload is skipped next time
    db.record_imported_file(content_hash, filename, result.institution, new_count)
    
    return jsonify({
        'success': True,
        'message': f'Imported {new_count} transactions',
        'new_count': new_count,
        'duplicate_count': duplicate_count,
        'total_parsed': len(transactions),
        'institution': result.institution,
        'warnings': result.warnings
    })


# ==================== API: PLAID ====================

@app.route('/api/plaid/status', methods=['GET'])
def plaid_status():
    """Check whether Plaid is configured and list linked accounts."""
    service = get_plaid_service()
    return jsonify({
        'success': True,
        'configured': service is not None,
        'linked_accounts': db.get_linked_accounts()
    })


@app.route('/api/plaid/create-link-token', methods=['POST'])
def plaid_create_link_token():
    """Create a Plaid Link token to initialize the Link widget."""
    service = get_plaid_service()
    if service is None:
        return jsonify({
            'success': False,
            'error': 'Plaid is not configured. Set PLAID_CLIENT_ID and PLAID_SECRET in your .env file.'
        }), 400

    try:
        # Single-user local app, so a fixed user id is fine
        result = service.create_link_token(user_id='paisa-local-user')
        return jsonify({
            'success': True,
            'link_token': result['link_token']
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to create link token: {e}'}), 500


@app.route('/api/plaid/exchange-token', methods=['POST'])
def plaid_exchange_token():
    """Exchange a public token for an access token and save linked accounts."""
    service = get_plaid_service()
    if service is None:
        return jsonify({'success': False, 'error': 'Plaid is not configured.'}), 400

    data = request.get_json() or {}
    public_token = data.get('public_token')
    if not public_token:
        return jsonify({'success': False, 'error': 'public_token required'}), 400

    try:
        # Exchange for a permanent access token
        exchange = service.exchange_public_token(public_token)
        access_token = exchange['access_token']
        item_id = exchange['item_id']

        # Fetch institution + accounts for this item
        institution = service.get_institution(access_token)
        accounts = service.get_accounts(access_token)

        saved = 0
        for account in accounts:
            db.save_linked_account(
                account_id=account['account_id'],
                item_id=item_id,
                access_token=access_token,
                institution_id=institution['institution_id'],
                institution_name=institution['institution_name'],
                account_name=account['name'],
                account_type=account['type'],
                account_mask=account['mask'] or '',
            )
            saved += 1

        return jsonify({
            'success': True,
            'institution': institution['institution_name'],
            'accounts_linked': saved
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to link account: {e}'}), 500


@app.route('/api/plaid/sync', methods=['POST'])
def plaid_sync():
    """Sync transactions from all linked Plaid accounts into the database."""
    service = get_plaid_service()
    if service is None:
        return jsonify({'success': False, 'error': 'Plaid is not configured.'}), 400

    # Safe to import here: service is not None means plaid is installed.
    from src.services.plaid_service import convert_plaid_to_paisa

    data = request.get_json() or {}

    # Determine the sync window. Priority:
    #   1. explicit start_date (ISO 'YYYY-MM-DD')
    #   2. days count back from today
    #   3. default: start of the current calendar year (backfill YTD)
    # Plaid/the bank ultimately caps how far back data is actually available.
    end = date.today()
    if data.get('start_date'):
        try:
            start = date.fromisoformat(data['start_date'])
        except ValueError:
            return jsonify({'success': False, 'error': "start_date must be YYYY-MM-DD"}), 400
    elif data.get('days'):
        start = end - timedelta(days=int(data['days']))
    else:
        start = date(end.year, 1, 1)

    linked = db.get_linked_accounts_full()
    if not linked:
        return jsonify({'success': False, 'error': 'No linked accounts. Connect a bank first.'}), 400

    # Group accounts by access_token (one item can have multiple accounts)
    items = {}
    for acct in linked:
        token = acct['access_token']
        items.setdefault(token, {
            'institution_name': acct['institution_name'],
            'accounts': {}
        })
        items[token]['accounts'][acct['account_id']] = acct['account_name']

    total_new = 0
    total_duplicate = 0
    errors = []

    for access_token, info in items.items():
        try:
            plaid_txns = service.get_transactions(
                access_token=access_token,
                start_date=start,
                end_date=end,
            )
        except Exception as e:
            errors.append(f"{info['institution_name']}: {e}")
            continue

        account_names = info['accounts']
        new_txns = []
        for ptxn in plaid_txns:
            account_name = account_names.get(ptxn.account_id, info['institution_name'])
            tx_dict = convert_plaid_to_paisa(
                ptxn,
                institution_name=info['institution_name'],
                account_name=account_name,
            )
            new_txns.append(_plaid_dict_to_transaction(tx_dict))

        # Categorize and persist (skip duplicates by id)
        categorized = categorizer.categorize_all(new_txns)
        for tx in categorized:
            if db.transaction_exists(tx.id):
                total_duplicate += 1
            else:
                db.save_transaction(tx)
                total_new += 1

        # Mark each account in this item as synced
        for account_id in account_names:
            db.update_account_sync(account_id)

    # Auto-detect inter-account transfers across the freshly-synced data so
    # money moving between the user's own accounts isn't counted as spending.
    transfers_marked = 0
    try:
        tr = db.detect_transfers(day_window=3, apply=True)
        transfers_marked = tr.get('updated', 0)
    except Exception as e:
        errors.append(f"transfer detection: {e}")

    # Capture a net-worth snapshot so balance history builds up over time.
    try:
        _capture_balance_snapshot()
    except Exception as e:
        errors.append(f"snapshot: {e}")

    return jsonify({
        'success': True,
        'new_count': total_new,
        'duplicate_count': total_duplicate,
        'transfers_auto_marked': transfers_marked,
        'errors': errors,
        'from': start.isoformat(),
        'to': end.isoformat(),
        'message': f'Synced {total_new} new transactions ({start.isoformat()} to {end.isoformat()})'
    })


@app.route('/api/plaid/accounts', methods=['GET'])
def plaid_accounts():
    """
    Linked accounts grouped by institution, with live balances from Plaid.
    Falls back to stored metadata (no balance) if a balance fetch fails.
    """
    service = get_plaid_service()
    linked = db.get_linked_accounts_full()
    if not linked:
        return jsonify({'success': True, 'institutions': []})

    # Group stored accounts by institution; map account_id -> token for balances
    by_inst = {}
    token_for_account = {}
    for a in linked:
        token_for_account[a['account_id']] = a['access_token']
        inst = a['institution_name'] or 'Unknown'
        by_inst.setdefault(inst, {})

    # Fetch live balances per access_token (one call per item)
    balances = {}
    if service is not None:
        seen_tokens = set()
        for a in linked:
            tok = a['access_token']
            if tok in seen_tokens:
                continue
            seen_tokens.add(tok)
            try:
                for acct in service.get_accounts(tok):
                    balances[acct['account_id']] = acct
            except Exception:
                pass  # degrade gracefully; show metadata without balance

    institutions = []
    for a in linked:
        inst = a['institution_name'] or 'Unknown'
        bal = balances.get(a['account_id'], {})
        by_inst[inst][a['account_id']] = {
            'name': a['account_name'],
            'type': a['account_type'],
            'mask': a['account_mask'],
            'current_balance': bal.get('current_balance'),
            'available_balance': bal.get('available_balance'),
            'subtype': bal.get('subtype'),
        }

    for inst, accts in by_inst.items():
        acct_list = list(accts.values())
        total = sum(x['current_balance'] or 0 for x in acct_list)
        institutions.append({
            'institution': inst,
            'accounts': acct_list,
            'total_balance': round(total, 2),
        })
    institutions.sort(key=lambda x: x['institution'])

    return jsonify({'success': True, 'institutions': institutions})


def _capture_balance_snapshot():
    """Pull current balances from Plaid and store a net-worth snapshot.
    Returns number of accounts captured (0 if Plaid unavailable)."""
    service = get_plaid_service()
    if service is None:
        return 0
    linked = db.get_linked_accounts_full()
    if not linked:
        return 0

    snapshot_accounts = []
    seen_tokens = set()
    for a in linked:
        tok = a['access_token']
        if tok in seen_tokens:
            continue
        seen_tokens.add(tok)
        try:
            for acct in service.get_accounts(tok):
                snapshot_accounts.append({
                    'account_id': acct['account_id'],
                    'institution_name': a['institution_name'],
                    'account_name': acct.get('name'),
                    'account_type': acct.get('type'),
                    'subtype': acct.get('subtype'),
                    'current_balance': acct.get('current_balance'),
                })
        except Exception:
            pass
    return db.save_balance_snapshot(snapshot_accounts)


@app.route('/api/networth', methods=['GET'])
def get_networth():
    """Net worth history (assets - liabilities) over snapshot dates."""
    history = db.get_net_worth_history()
    return jsonify({'success': True, 'history': history})


@app.route('/api/networth/capture', methods=['POST'])
def capture_networth():
    """Capture a fresh balance snapshot now."""
    n = _capture_balance_snapshot()
    return jsonify({'success': True, 'accounts_captured': n})


@app.route('/api/plaid/liabilities', methods=['GET'])
def plaid_liabilities():
    """
    Return mortgage / loan / credit liability details across linked items.
    Requires the 'liabilities' product enabled on the Plaid account and
    requested at link time (PLAID_PRODUCTS). Degrades gracefully otherwise.
    """
    service = get_plaid_service()
    if service is None:
        return jsonify({'success': False, 'error': 'Plaid is not configured.'}), 400

    linked = db.get_linked_accounts_full()
    tokens = {a['access_token']: a['institution_name'] for a in linked}
    if not tokens:
        return jsonify({'success': False, 'error': 'No linked accounts.'}), 400

    out = []
    errors = []
    for token, inst in tokens.items():
        try:
            data = service.get_liabilities(token)
            out.append({'institution': inst, 'liabilities': data})
        except Exception as e:
            # Most commonly: product not enabled for this item/account
            errors.append(f"{inst}: {e}")

    return jsonify({'success': True, 'items': out, 'errors': errors})


@app.route('/api/plaid/investments', methods=['POST'])
def plaid_investments():
    """
    Sync investment transactions (buys/sells/dividends) into the database.
    Requires the 'investments' product enabled + requested at link time.
    """
    service = get_plaid_service()
    if service is None:
        return jsonify({'success': False, 'error': 'Plaid is not configured.'}), 400

    data = request.get_json() or {}
    start = None
    if data.get('start_date'):
        try:
            start = date.fromisoformat(data['start_date'])
        except ValueError:
            return jsonify({'success': False, 'error': 'start_date must be YYYY-MM-DD'}), 400

    linked = db.get_linked_accounts_full()
    tokens = {a['access_token']: a for a in linked}
    if not tokens:
        return jsonify({'success': False, 'error': 'No linked accounts.'}), 400

    total_new = 0
    errors = []
    for token, acct in tokens.items():
        try:
            inv_txns = service.get_investment_transactions(token, start_date=start)
        except Exception as e:
            errors.append(f"{acct['institution_name']}: {e}")
            continue

        for it in inv_txns:
            # Positive Plaid investment amount = cash out of account (buy) => debit
            amount = abs(it['amount'])
            ttype = TransactionType.DEBIT if it['amount'] > 0 else TransactionType.CREDIT
            tx = Transaction(
                id=it['investment_transaction_id'],
                date=it['date'],
                description=it['name'],
                amount=amount,
                transaction_type=ttype,
                account_id=it['account_id'],
                institution=acct['institution_name'],
                category='Investments',
                original_description=it['name'],
                source_type='plaid',
            )
            tx = categorizer.categorize_transaction(tx)
            if not db.transaction_exists(tx.id):
                db.save_transaction(tx)
                total_new += 1

    return jsonify({'success': True, 'new_count': total_new, 'errors': errors})


@app.route('/api/plaid/unlink/<account_id>', methods=['DELETE'])
def plaid_unlink(account_id):
    """Remove a linked Plaid account."""
    success = db.delete_linked_account(account_id)
    if success:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Account not found'}), 404


def _plaid_dict_to_transaction(tx_dict: dict) -> Transaction:
    """Convert the dict from convert_plaid_to_paisa() into a Transaction object."""
    return Transaction(
        id=tx_dict['id'],
        date=tx_dict['date'],
        description=tx_dict['description'],
        amount=tx_dict['amount'],
        transaction_type=tx_dict['transaction_type'],
        account_id=tx_dict['account_id'],
        institution=tx_dict['institution'],
        category=tx_dict.get('category', 'Uncategorized'),
        merchant_name=tx_dict.get('merchant_name', ''),
        original_description=tx_dict.get('description', ''),
        source_type='plaid',
    )


# ==================== API: TRANSACTIONS ====================

@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    """Get transactions with filters."""
    # Parse query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    category = request.args.get('category')
    account_id = request.args.get('account')
    min_amount = request.args.get('min_amount', type=float)
    max_amount = request.args.get('max_amount', type=float)
    search = request.args.get('search')
    uncategorized = request.args.get('uncategorized', 'false').lower() == 'true'
    limit = request.args.get('limit', 500, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    # Convert date strings
    start = date.fromisoformat(start_date) if start_date else None
    end = date.fromisoformat(end_date) if end_date else None
    
    transactions = db.get_transactions(
        start_date=start,
        end_date=end,
        category=category,
        account_id=account_id,
        min_amount=min_amount,
        max_amount=max_amount,
        search=search,
        uncategorized_only=uncategorized,
        limit=limit,
        offset=offset
    )
    
    return jsonify({
        'success': True,
        'transactions': [tx.to_dict() for tx in transactions],
        'count': len(transactions)
    })


@app.route('/api/transactions/<tx_id>/category', methods=['PUT'])
def update_transaction_category(tx_id):
    """Update a transaction's category."""
    data = request.get_json()
    category = data.get('category')
    
    if not category:
        return jsonify({'success': False, 'error': 'Category required'}), 400
    
    success = db.update_transaction_category(tx_id, category)
    
    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Transaction not found'}), 404


@app.route('/api/transactions/bulk-categorize', methods=['POST'])
def bulk_categorize():
    """Categorize multiple transactions at once."""
    data = request.get_json()
    tx_ids = data.get('transaction_ids', [])
    category = data.get('category')
    
    if not category:
        return jsonify({'success': False, 'error': 'Category required'}), 400
    
    updated = 0
    for tx_id in tx_ids:
        if db.update_transaction_category(tx_id, category):
            updated += 1
    
    return jsonify({
        'success': True,
        'updated': updated
    })


# ==================== API: RULES ====================

@app.route('/api/rules', methods=['GET'])
def get_rules():
    """Get all categorization rules."""
    rules = db.get_rules()
    return jsonify({
        'success': True,
        'rules': [r.to_dict() for r in rules]
    })


@app.route('/api/rules', methods=['POST'])
def add_rule():
    """Add a new categorization rule."""
    data = request.get_json()
    pattern = data.get('pattern')
    category = data.get('category')
    apply_existing = data.get('apply_existing', False)
    
    if not pattern or not category:
        return jsonify({'success': False, 'error': 'Pattern and category required'}), 400
    
    success = categorizer.add_rule(pattern, category)
    
    if not success:
        return jsonify({'success': False, 'error': 'Failed to add rule'}), 500
    
    updated = 0
    if apply_existing:
        updated = categorizer.apply_rule_to_existing(pattern, category)
    
    return jsonify({
        'success': True,
        'applied_to': updated
    })


@app.route('/api/rules/<int:rule_id>', methods=['DELETE'])
def delete_rule(rule_id):
    """Delete a rule."""
    success = db.delete_rule(rule_id)
    
    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Rule not found'}), 404


# ==================== API: CATEGORIES ====================

@app.route('/api/categories', methods=['GET'])
def get_categories():
    """Get all categories."""
    categories = db.get_categories()
    return jsonify({
        'success': True,
        'categories': categories
    })


@app.route('/api/categories', methods=['POST'])
def add_category():
    """Add a new category."""
    data = request.get_json()
    name = data.get('name')
    icon = data.get('icon', '📦')
    color = data.get('color', '#9ca3af')
    
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400
    
    success = db.add_category(name, icon, color)
    
    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Failed to add category'}), 500


# ==================== API: DASHBOARD ====================

@app.route('/api/summary', methods=['GET'])
def get_summary():
    """Get summary statistics."""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    start = date.fromisoformat(start_date) if start_date else None
    end = date.fromisoformat(end_date) if end_date else None
    
    summary = db.get_summary(start, end)
    
    return jsonify({
        'success': True,
        **summary
    })


@app.route('/api/trend', methods=['GET'])
def get_trend():
    """Income vs expenses per month (Transfers excluded)."""
    months = request.args.get('months', 12, type=int)
    trend = db.get_monthly_trend(months=months)
    return jsonify({'success': True, 'trend': trend})


# ==================== API: BUDGETS ====================

@app.route('/api/budgets', methods=['GET'])
def get_budgets():
    """Budget vs actual for a given month (defaults to current month)."""
    today = date.today()
    year = request.args.get('year', today.year, type=int)
    month = request.args.get('month', today.month, type=int)
    status = db.get_budget_status(year, month)
    total_limit = round(sum(s['monthly_limit'] for s in status), 2)
    total_spent = round(sum(s['spent'] for s in status), 2)
    return jsonify({
        'success': True,
        'year': year,
        'month': month,
        'budgets': status,
        'total_limit': total_limit,
        'total_spent': total_spent,
    })


@app.route('/api/budgets', methods=['POST'])
def set_budget():
    """Create or update a category budget."""
    data = request.get_json() or {}
    category = data.get('category')
    limit = data.get('monthly_limit')
    if not category or limit is None:
        return jsonify({'success': False, 'error': 'category and monthly_limit required'}), 400
    try:
        limit = float(limit)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'monthly_limit must be a number'}), 400
    if limit < 0:
        return jsonify({'success': False, 'error': 'monthly_limit must be >= 0'}), 400
    ok = db.set_budget(category, limit)
    return jsonify({'success': ok})


@app.route('/api/budgets/<category>', methods=['DELETE'])
def delete_budget(category):
    """Delete a category budget."""
    ok = db.delete_budget(category)
    return jsonify({'success': ok})


# ==================== API: TRANSFER DETECTION ====================

@app.route('/api/detect-transfers', methods=['GET', 'POST'])
def detect_transfers():
    """
    GET  = preview likely inter-account transfers (no changes).
    POST = apply: mark both legs of each matched pair as Transfer.
    """
    apply = request.method == 'POST'
    window = request.args.get('day_window', 3, type=int)
    result = db.detect_transfers(day_window=window, apply=apply)
    return jsonify({'success': True, **result})


# ==================== API: RECURRING ====================

@app.route('/api/recurring', methods=['GET'])
def get_recurring():
    """Detected recurring charges (subscriptions, loans, bills)."""
    min_occ = request.args.get('min_occurrences', 3, type=int)
    lookback = request.args.get('lookback_months', 6, type=int)
    items = db.get_recurring(min_occurrences=min_occ, lookback_months=lookback)
    est_total = round(sum(i['est_monthly'] for i in items), 2)
    return jsonify({
        'success': True,
        'recurring': items,
        'estimated_monthly_total': est_total,
        'count': len(items),
    })


@app.route('/api/merchants', methods=['GET'])
def get_top_merchants():
    """Get top merchants by spending."""
    limit = request.args.get('limit', 10, type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    start = date.fromisoformat(start_date) if start_date else None
    end = date.fromisoformat(end_date) if end_date else None
    
    merchants = db.get_top_merchants(limit, start, end)
    
    return jsonify({
        'success': True,
        'merchants': merchants
    })


# ==================== API: UNCATEGORIZED REVIEW ====================

@app.route('/api/uncategorized', methods=['GET'])
def get_uncategorized():
    """Get uncategorized transactions for review."""
    limit = request.args.get('limit', 50, type=int)
    transactions = db.get_uncategorized_transactions(limit)
    
    # For each transaction, suggest a rule pattern
    suggestions = []
    for tx in transactions:
        suggestion = categorizer.suggest_rule(tx)
        suggestions.append({
            'transaction': tx.to_dict(),
            'suggested_pattern': suggestion
        })
    
    return jsonify({
        'success': True,
        'transactions': suggestions,
        'count': len(suggestions)
    })


# ==================== HEALTH CHECK ====================

@app.route('/api/health')
def health():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'version': '1.0.0'})


def create_app():
    """Application factory."""
    return app


if __name__ == '__main__':
    app.run(debug=True, port=5000)
