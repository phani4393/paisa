# 💰 Paisa - Personal Finance Tracker

A seamless, local-first personal finance tracker that parses bank statements (PDF & CSV), auto-categorizes transactions, and provides beautiful spending insights. All data stays on your machine.

![Dashboard](docs/dashboard-preview.png)

## ✨ Features

- **📤 Drag & Drop Import** - Upload PDF or CSV bank statements with ease
- **🏦 Multi-Bank Support** - Works with Chase, Citi, PNC, Bank of America, Wells Fargo, and more
- **🤖 Smart Auto-Categorization** - Rule-based engine learns your spending patterns
- **📊 Beautiful Dashboard** - Visual spending breakdown by category and top merchants
- **🔍 Granular Filters** - Search and filter by date, category, amount, merchant
- **📱 Responsive Design** - Works on desktop and mobile browsers
- **🔒 Privacy First** - 100% local SQLite database, no cloud, no tracking
- **⚡ Fast & Lightweight** - Python Flask backend, vanilla JS frontend

## 🚀 Quick Start

### Prerequisites

- Python 3.10 or higher
- pip (Python package manager)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/paisa.git
   cd paisa
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   python run.py
   ```

4. **Open your browser**
   
   The app will automatically open at [http://localhost:5000](http://localhost:5000)

## 📖 How to Use

### Importing Statements

1. Click **"Import Statement"** button on the Transactions page
2. Drag & drop your bank statement (PDF or CSV) or click to browse
3. Paisa will parse the file, extract transactions, and auto-categorize them
4. Review the import summary showing new vs duplicate transactions

### Supported File Formats

| Format | Description |
|--------|-------------|
| **PDF** | Bank statement PDFs from most major banks |
| **CSV** | Exported transaction CSV files from bank websites |
| **Excel** | .xlsx and .xls files (converted to CSV internally) |

### Viewing Transactions

- Use the **Transactions** tab to see all imported transactions
- Filter by date range, category, amount range, or search text
- Click on a transaction's category badge to change its category
- Select multiple transactions for bulk categorization

### Categorizing Transactions

1. Go to the **Categorize** tab to see uncategorized transactions
2. Click **"Categorize"** on any transaction
3. Select the appropriate category
4. Optionally create a rule to auto-categorize similar future transactions

### Managing Rules

- The **Rules** tab shows all categorization rules
- Rules match text patterns in transaction descriptions
- Higher match counts indicate frequently used rules
- Add custom rules with the **"+ Add Rule"** button
- Delete rules that are no longer needed

### Dashboard Insights

The **Dashboard** provides:
- Total income, expenses, and net cash flow
- Savings rate percentage
- Spending breakdown by category with visual bars
- Top merchants by spending amount

## 🏗️ Project Structure

```
paisa/
├── run.py                 # Application entry point
├── requirements.txt       # Python dependencies
├── README.md             # This file
├── FAQ.md                # Frequently Asked Questions
├── src/
│   ├── app.py            # Flask web application & API routes
│   ├── database.py       # SQLite database manager
│   ├── models.py         # Data models & default categories
│   ├── categorizer.py    # Rule-based categorization engine
│   └── parsers/
│       ├── parser_factory.py    # Auto-detects file type
│       ├── base_parser.py       # Base parser class
│       ├── generic_csv_parser.py  # CSV file parser
│       └── generic_pdf_parser.py  # PDF file parser
├── templates/
│   └── index.html        # Main HTML template
├── static/
│   ├── style.css         # Application styles
│   └── app.js            # Frontend JavaScript
└── data/
    ├── paisa.db          # SQLite database (created on first run)
    └── uploads/          # Uploaded statement files
```

## 🛠️ Configuration

### Default Categories

Paisa comes with 18 pre-configured categories:

| Category | Icon | Common Matches |
|----------|------|----------------|
| Income | 💰 | Payroll, Direct Deposit |
| Housing | 🏠 | Rent, Mortgage |
| Groceries | 🛒 | Costco, Walmart, Target |
| Dining | 🍽️ | Restaurants, DoorDash |
| Auto | 🚗 | Gas, Parking, Tolls |
| Utilities | 💡 | Electric, Internet, Phone |
| Subscriptions | 📱 | Netflix, Spotify, Apple |
| Shopping | 🛍️ | Amazon, Online stores |
| Health | 💊 | Pharmacy, Medical |
| Entertainment | 🎬 | Movies, Events |
| Travel | ✈️ | Airlines, Hotels |
| And more... | | |

### Adding Custom Categories

Categories can be added via the API:
```bash
curl -X POST http://localhost:5000/api/categories \
  -H "Content-Type: application/json" \
  -d '{"name": "Charity", "icon": "❤️", "color": "#ec4899"}'
```

## 📡 API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/upload` | POST | Upload and parse a statement file |
| `/api/transactions` | GET | Get transactions with filters |
| `/api/transactions/<id>/category` | PUT | Update transaction category |
| `/api/summary` | GET | Get dashboard summary statistics |
| `/api/categories` | GET | Get all categories |
| `/api/rules` | GET/POST | Get or create categorization rules |
| `/api/rules/<id>` | DELETE | Delete a rule |
| `/api/uncategorized` | GET | Get uncategorized transactions |
| `/api/merchants` | GET | Get top merchants by spending |

## 🔧 Troubleshooting

### PDF parsing not working
- Ensure `pdfplumber` is installed: `pip install pdfplumber`
- Some bank PDFs use images instead of text - these require OCR (not yet supported)

### Import shows 0 transactions
- Check that the file is a valid bank statement
- Ensure the PDF contains selectable text (not scanned images)
- Try exporting as CSV from your bank's website instead

### Port 5000 already in use
- Edit `run.py` and change the port number
- Or stop the other application using port 5000

## 🤝 Contributing

Contributions are welcome! Areas for improvement:

- [ ] Add bank-specific parsers for better accuracy
- [ ] OCR support for scanned PDFs
- [ ] Recurring transaction detection
- [ ] Budget setting and tracking
- [ ] Export to CSV/Excel
- [ ] Dark/light theme toggle
- [ ] Charts and graphs

## 📄 License

MIT License - feel free to use, modify, and distribute.

## 🙏 Credits

Built with:
- [Flask](https://flask.palletsprojects.com/) - Python web framework
- [pdfplumber](https://github.com/jsvine/pdfplumber) - PDF text extraction
- [SQLite](https://sqlite.org/) - Local database

---

**Paisa** (पैसा) means "money" in Hindi/Telugu. Track your paisa, grow your wealth! 💰
