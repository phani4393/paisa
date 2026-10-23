"""
Flask web application for Paisa.
"""
import os
from pathlib import Path
from datetime import datetime, date
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

from src.database import Database
from src.categorizer import Categorizer
from src.parsers.parser_factory import ParserFactory


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
    
    # Save file
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_filename = f"{timestamp}_{filename}"
    file_path = Path(app.config['UPLOAD_FOLDER']) / unique_filename
    file.save(str(file_path))
    
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
    
    return jsonify({
        'success': True,
        'message': f'Imported {new_count} transactions',
        'new_count': new_count,
        'duplicate_count': duplicate_count,
        'total_parsed': len(transactions),
        'institution': result.institution,
        'warnings': result.warnings
    })


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
