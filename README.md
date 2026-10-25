# 💰 Paisa - Personal Finance Tracker

A local-first personal finance tracker. Connect your banks automatically with
**Plaid**, or import PDF/CSV statements by hand. Paisa auto-categorizes your
transactions and shows spending trends, account balances, and category
breakdowns. All of your data stays on your own machine in a local SQLite
database.

## ✨ Features

- **🏦 Automatic bank sync (Plaid)** — Connect banks, cards, loans, and brokerage accounts and pull transactions automatically
- **📤 Manual import fallback** — Drag & drop PDF, CSV, or Excel statements
- **🏦 Multi-bank parsers** — Dedicated parsers for Chase, Citi, PNC, and Robinhood, plus generic CSV/PDF
- **🤖 Rule-based auto-categorization** — Learns your patterns; rules apply to future imports and syncs
- **📊 Rich dashboard** — Monthly income-vs-expenses trend, spending donut, category breakdown, top merchants, and per-institution account balances
- **📅 Date presets** — This Month / Last 3 Months / YTD / Last 12 Months / All Time
- **🔍 Granular filters** — Search and filter by date, category, amount, merchant
- **🔒 Privacy first** — 100% local SQLite; credentials live only in your local `.env`

## 🚀 Quick Start

### Prerequisites

- **Python 3.11** recommended (3.10–3.12 should work). See the note below about
  Python 3.13+ and the `plaid-python` build.
- [`uv`](https://docs.astral.sh/uv/) recommended for fast installs (or plain `pip`).
- A [Plaid account](https://dashboard.plaid.com/) if you want automatic bank
  sync. The manual statement import works without Plaid.

### 1. Clone

```bash
git clone https://github.com/phani4393/paisa.git
cd paisa
```

### 2. Create a virtual environment and install dependencies

A virtual environment is **strongly recommended**. Plaid is only available to
the interpreter that has the dependencies installed, so you'll run the app with
that environment's Python.

Using `uv` (fast):

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt   # Windows
# uv pip install --python .venv/bin/python -r requirements.txt         # macOS/Linux
```

Using plain `pip`:

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

> **⚠️ Note on `plaid-python` install time.** `plaid-python` ships source-only
> (no prebuilt wheels) and builds from source. `requirements.txt` pins the `9.x`
> line on purpose — newer major versions (40.x+) generate thousands of model
> files and can take many minutes (or appear to hang) to build, especially on
> Python 3.13+. If install stalls, make sure you're on Python 3.11 and using the
> pinned version.

### 3. (Optional) Configure Plaid for automatic bank sync

Skip this section if you only want manual statement imports — the app runs fine
without Plaid (the "Connect Bank" button just stays disabled).

1. Copy the example env file and open it:

   ```bash
   cp .env.example .env            # macOS/Linux
   Copy-Item .env.example .env     # Windows PowerShell
   ```

2. Get your keys from the [Plaid Dashboard → Developers → Keys](https://dashboard.plaid.com/developers/keys)
   and fill in `.env`:

   ```ini
   PLAID_CLIENT_ID=your_client_id
   PLAID_SECRET=your_secret           # must match PLAID_ENV below
   PLAID_ENV=sandbox                  # sandbox | production
   # Optional: also pull mortgage/loan + brokerage data when available
   PLAID_PRODUCTS=transactions,liabilities,investments
   ```

   - **sandbox** — test banks with fake data. Log in with username `user_good` /
     password `pass_good`. Great for trying the flow first.
   - **production** — real bank logins and your real transactions. Each
     environment has its **own secret** — use the one that matches `PLAID_ENV`.
   - Production access may require approval/billing setup in your Plaid
     dashboard. A free trial typically allows up to ~10 connected institutions.

3. `.env` is git-ignored and never committed. Keep your keys private.

### 4. Run

```bash
.venv\Scripts\python.exe run.py      # Windows
# .venv/bin/python run.py            # macOS/Linux
```

The app opens automatically at [http://localhost:5000](http://localhost:5000).

> Running `python run.py` with your system Python (outside the venv) also works,
> but Plaid features will be disabled unless that interpreter has the
> dependencies installed. Prefer the venv's Python.

## 📖 How to Use

### Option A — Connect a bank with Plaid (automatic)

1. Go to the **Transactions** tab and click **🏦 Connect Bank**.
2. Log in to your bank through Plaid's secure popup. (Paisa never sees your bank
   password — only the resulting transactions.)
3. Repeat for each institution you want to connect.
4. Click **🔄 Sync** to pull transactions. By default it backfills from the start
   of the current year; the actual history depth is set by each bank (often
   ~90 days to a year on first connect).

### Option B — Import a statement (manual)

1. Click **📤 Import Statement** on the Transactions page.
2. Drag & drop a PDF, CSV, or Excel statement, or click to browse.
3. Paisa detects the bank, parses transactions, auto-categorizes, and skips
   duplicates (including re-uploads of the same file).

Use manual import for history older than Plaid can reach, or for banks you don't
want to connect.

### Categorizing & rules

- The **Categorize** tab lists uncategorized transactions.
- The **Rules** tab manages pattern → category rules. A rule auto-categorizes
  matching transactions on every future import and sync. Check "apply to
  existing" to backfill current uncategorized transactions.
- Tip: mark transfers between your own accounts (card payments, brokerage
  transfers, etc.) as **Transfer** so they don't inflate income/expenses.

### Dashboard

The **Dashboard** shows:
- Income, Expenses, Net Cash Flow, and Savings Rate (Transfers excluded)
- **Monthly trend** — income vs expenses bar chart over time
- **Spending donut** + category breakdown
- **Top merchants** (normalized, so store-number variants merge)
- **Accounts** — linked accounts grouped by institution with live balances
- Date-range presets and a custom range picker

## 🏗️ Project Structure

```
paisa/
├── run.py                        # Application entry point
├── requirements.txt              # Python dependencies
├── .env.example                  # Template for Plaid credentials (copy to .env)
├── README.md
├── FAQ.md
├── src/
│   ├── app.py                    # Flask app & API routes (incl. Plaid)
│   ├── database.py               # SQLite manager + analytics
│   ├── models.py                 # Data models & default categories
│   ├── categorizer.py            # Rule-based categorization engine
│   ├── services/
│   │   └── plaid_service.py      # Plaid API wrapper (link/sync/liabilities/investments)
│   └── parsers/
│       ├── parser_factory.py     # Auto-detects file type / institution
│       ├── base_parser.py        # Base parser class
│       ├── chase_parser.py       # Chase statements
│       ├── citi_parser.py        # Citi statements
│       ├── pnc_parser.py         # PNC Virtual Wallet statements
│       ├── robinhood_parser.py   # Robinhood PDF statements + card CSV
│       ├── generic_csv_parser.py # Fallback CSV parser
│       └── generic_pdf_parser.py # Fallback PDF parser
├── templates/
│   └── index.html
├── static/
│   ├── style.css
│   ├── app.js                    # Dashboard, transactions, rules UI
│   └── plaid.js                  # Plaid Link connect / sync flow
└── data/                         # git-ignored
    ├── paisa.db                  # SQLite database (created on first run)
    └── uploads/                  # Uploaded statement files
```

## 📡 API Reference

### Core

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/upload` | POST | Upload and parse a statement file |
| `/api/transactions` | GET | Get transactions with filters |
| `/api/transactions/<id>/category` | PUT | Update a transaction's category |
| `/api/transactions/bulk-categorize` | POST | Bulk-categorize transactions |
| `/api/summary` | GET | Dashboard summary statistics |
| `/api/trend` | GET | Monthly income vs expenses (Transfers excluded) |
| `/api/merchants` | GET | Top merchants by spending (normalized) |
| `/api/categories` | GET/POST | Get or add categories |
| `/api/rules` | GET/POST | Get or create categorization rules |
| `/api/rules/<id>` | DELETE | Delete a rule |
| `/api/uncategorized` | GET | Uncategorized transactions for review |

### Plaid

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/plaid/status` | GET | Whether Plaid is configured + linked accounts |
| `/api/plaid/create-link-token` | POST | Create a Plaid Link token |
| `/api/plaid/exchange-token` | POST | Exchange public token, save accounts |
| `/api/plaid/sync` | POST | Sync transactions (defaults to YTD) |
| `/api/plaid/accounts` | GET | Linked accounts + live balances by institution |
| `/api/plaid/liabilities` | GET | Mortgage/loan/credit details (if enabled) |
| `/api/plaid/investments` | POST | Sync brokerage transactions (if enabled) |
| `/api/plaid/unlink/<account_id>` | DELETE | Remove a linked account |

## 🔧 Troubleshooting

**`plaid-python` install hangs or takes forever**
Use Python 3.11 and the pinned `9.x` version in `requirements.txt`. Newer major
versions build very slowly from source. There are no prebuilt wheels for any
version, so some build time is expected.

**"Connect Bank" is disabled / `/api/plaid/status` shows `configured: false`**
Plaid isn't configured. Create `.env` from `.env.example` and set
`PLAID_CLIENT_ID` / `PLAID_SECRET`, then restart the app with the venv's Python.

**`INVALID_API_KEYS` from Plaid**
The secret must match `PLAID_ENV` (sandbox secret with `sandbox`, production
secret with `production`). Also confirm production access is approved in your
Plaid dashboard. Restart the app after editing `.env` — it's read at startup.

**"No liability accounts / connect a different bank" during Connect Bank**
This happens if liabilities/investments are requested as *required* products.
Paisa requests them as optional, so update to the latest code if you see this.

**Sync returns only ~90 days of history**
That's the bank's limit via Plaid, not a bug. Use manual statement import for
older history; future syncs keep accumulating new transactions.

**PDF import finds 0 transactions**
The PDF may be scanned images rather than selectable text (OCR isn't supported).
Try exporting CSV from your bank instead.

**Port 5000 already in use**
Edit the port in `run.py`, or stop the other app using 5000.

## 🤝 Contributing

Ideas welcome:

- [ ] Budgets and goals (budget-vs-actual per category)
- [ ] More bank-specific parsers
- [ ] OCR for scanned PDFs
- [ ] Recurring transaction detection
- [ ] Dashboard UI for liabilities & investments data
- [ ] Export to CSV/Excel

## 📄 License

MIT License — free to use, modify, and distribute.

## 🙏 Credits

Built with [Flask](https://flask.palletsprojects.com/),
[Plaid](https://plaid.com/docs/),
[pdfplumber](https://github.com/jsvine/pdfplumber), and
[SQLite](https://sqlite.org/).

---

**Paisa** (पैसा / పైసా) means "money." Track your paisa, grow your wealth! 💰
