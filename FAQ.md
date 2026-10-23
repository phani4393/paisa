# ❓ Frequently Asked Questions (FAQ)

## General Questions

### What is Paisa?
Paisa is a local-first personal finance tracker that helps you understand your spending by importing bank statements, automatically categorizing transactions, and providing visual insights into your finances.

### Why is it called "Paisa"?
"Paisa" (पैसा) means "money" in Hindi, Urdu, and Telugu. It's a common term used across South Asia for currency/money.

### Is Paisa free?
Yes, Paisa is completely free and open source under the MIT license.

### Does Paisa connect to my bank?
No. Paisa is a **local-first** application that works entirely offline. You manually download statements from your bank and import them into Paisa. This approach is more secure and doesn't require sharing your bank credentials.

---

## Privacy & Security

### Where is my data stored?
All your data is stored locally on your computer in a SQLite database file (`data/paisa.db`). Nothing is sent to any server or cloud service.

### Is my financial data secure?
Yes. Since all data stays on your local machine, you have complete control. There's no cloud sync, no accounts to create, and no data leaves your computer.

### Can I back up my data?
Yes! Simply copy the `data/paisa.db` file to your backup location. To restore, copy it back.

### How do I delete all my data?
Delete the `data/` folder in the Paisa directory. On next startup, a fresh database will be created.

---

## Importing Statements

### Which banks are supported?
Paisa uses generic parsers that work with most banks including:
- Chase
- Bank of America
- Citi
- PNC
- Wells Fargo
- Capital One
- Discover
- US Bank
- And most others that provide PDF or CSV statements

### What file formats are supported?
- **PDF** - Bank statement PDFs
- **CSV** - Transaction exports from bank websites
- **Excel** - .xlsx and .xls files

### My PDF import shows 0 transactions. Why?
This usually happens when:
1. The PDF is a scanned image rather than text-based
2. The bank uses an unusual format
3. The PDF is password-protected

**Solution:** Try downloading a CSV export from your bank's website instead.

### How do I export CSV from my bank?
Most banks offer this option:
1. Log into your online banking
2. Go to your account/transaction history
3. Look for "Download," "Export," or "Download Transactions"
4. Select CSV format and date range
5. Import the downloaded file into Paisa

### Does Paisa handle duplicate transactions?
Yes! Paisa generates unique IDs for each transaction based on date, description, and amount. If you import the same statement twice, duplicates are automatically skipped.

### Can I import multiple statements at once?
Currently, you import one file at a time. However, you can quickly import multiple files in succession through the UI.

---

## Categories & Rules

### What categories come pre-configured?
Paisa includes 18 default categories:
- Income, Housing, Groceries, Dining, Auto, Gas
- Utilities, Subscriptions, Shopping, Health
- Entertainment, Travel, Insurance, Fees
- ATM, Transfer, Other, Uncategorized

### How does auto-categorization work?
Paisa uses pattern-matching rules. When you import transactions:
1. Each transaction description is checked against all rules
2. Rules match case-insensitively (e.g., "COSTCO" matches "Costco Wholesale")
3. The first matching rule assigns the category
4. Unmatched transactions go to "Uncategorized"

### How do I create a new rule?
1. Go to the **Categorize** tab
2. Find an uncategorized transaction
3. Click **"Categorize"** and select a category
4. When prompted, choose to create a rule
5. The rule will auto-categorize similar future transactions

Or manually:
1. Go to the **Rules** tab
2. Click **"+ Add Rule"**
3. Enter a pattern (e.g., "STARBUCKS") and select a category

### Can I edit an existing rule?
Currently, you need to delete the old rule and create a new one with the updated pattern/category.

### What's a good rule pattern?
Use distinctive parts of merchant names:
- ✅ Good: `COSTCO`, `NETFLIX`, `SHELL`
- ❌ Too broad: `PAYMENT`, `PURCHASE`, `CARD`

### Can I have multiple rules for the same category?
Yes! You can create as many rules as needed. For example, both "SHELL" and "EXXON" can map to "Gas."

---

## Transactions

### How do I change a transaction's category?
1. Go to the **Transactions** tab
2. Find the transaction
3. Click on the category badge
4. Select the new category from the picker

### Can I edit transaction descriptions?
Currently, transaction descriptions are read-only to preserve the original bank data. The app shows both cleaned and original descriptions.

### How do I delete a transaction?
This feature is not currently available in the UI to prevent accidental data loss. If needed, you can delete directly from the SQLite database.

### What's the difference between "description" and "original description"?
- **Original description**: The raw text from your bank statement
- **Description**: A cleaned version with common prefixes removed (like "DEBIT CARD PURCHASE")

### Can I search for transactions?
Yes! Use the search box on the Transactions page. It searches across descriptions, merchant names, and original descriptions.

---

## Dashboard & Insights

### Why does the dashboard show $0?
The dashboard filters by date range. Make sure your selected dates include when your transactions occurred. Adjust the start/end dates and click **Apply**.

### How is "Savings Rate" calculated?
`Savings Rate = (Income - Expenses) / Income × 100`

Transfer transactions are excluded from both income and expenses to avoid double-counting.

### Why don't transfers show in spending?
Transfers between your own accounts (credit card payments, savings transfers, etc.) are excluded from income/expense totals since they don't represent actual earning or spending.

### Can I see spending trends over time?
Not yet - this is a planned feature. Currently, you can manually adjust date ranges to compare different periods.

---

## Technical Questions

### What technology stack does Paisa use?
- **Backend:** Python 3.10+, Flask
- **Database:** SQLite
- **Frontend:** Vanilla JavaScript, CSS
- **PDF Parsing:** pdfplumber, PyPDF2
- **CSV Parsing:** Python csv module, pandas

### Can I run Paisa on a server?
Yes, but it's designed for single-user local use. For server deployment:
1. Change the host from `127.0.0.1` to `0.0.0.0` in `run.py`
2. Use a production WSGI server like Gunicorn
3. Add authentication (not included by default)

### How do I change the port?
Edit `run.py` and change `port=5000` to your desired port number.

### Can I access Paisa from my phone?
If running on a computer, you can access it from other devices on the same network:
1. Find your computer's IP address
2. Ensure firewall allows port 5000
3. Access `http://YOUR_IP:5000` from your phone

### Where are uploaded files stored?
Uploaded statement files are saved to `data/uploads/` with timestamps to prevent conflicts.

---

## Troubleshooting

### The app won't start
1. Check Python is installed: `python --version`
2. Ensure dependencies are installed: `pip install -r requirements.txt`
3. Check nothing else is using port 5000

### Import is very slow
Large PDFs with many pages can take time. For faster imports:
- Use CSV exports when possible
- Import smaller date ranges

### Categories aren't showing
Try refreshing the browser. If the issue persists, check the browser console for errors.

### Rules aren't applying to new imports
Rules are case-insensitive but match exact substrings. Verify:
1. The pattern exists in the transaction description
2. The rule is listed in the Rules tab
3. Restart the app if you manually edited the database

### How do I reset everything?
1. Stop the app
2. Delete the `data/` folder
3. Restart the app - a fresh database will be created

---

## Feature Requests

### Will you add Plaid/bank connections?
No plans currently. The manual import approach is intentional for privacy. Many users prefer not to share bank credentials with third-party services.

### Can you add budgeting features?
This is on the roadmap! Future versions may include:
- Monthly budget limits per category
- Budget vs actual tracking
- Alerts when approaching limits

### Will you add charts and graphs?
Yes, this is planned. Potential additions:
- Spending over time line charts
- Category pie charts
- Month-over-month comparisons

### Can you support [specific bank]?
Paisa uses generic parsers, but bank-specific parsers improve accuracy. Open an issue with a (redacted) sample statement and we can look into it.

### Mobile app?
No native app is planned, but the web interface is mobile-responsive. You can add it to your home screen as a PWA.

---

## Getting Help

### I found a bug!
Please open an issue on GitHub with:
1. What you were trying to do
2. What happened instead
3. Browser and OS information
4. Any error messages

### I have a suggestion!
Open a GitHub issue with the "enhancement" label. We welcome ideas!

### Can I contribute code?
Absolutely! See the Contributing section in README.md.

---

*Last updated: October 2026*
