# 📖 Paisa — Usage Guide

A detailed, practical walkthrough of how to use Paisa and what to expect from
each feature. For install/setup, see [README.md](README.md); this guide assumes
the app is running at [http://localhost:5000](http://localhost:5000).

---

## Table of contents

1. [The big picture](#the-big-picture)
2. [Getting your transactions in](#getting-your-transactions-in)
3. [Categorizing & rules](#categorizing--rules)
4. [The dashboard, panel by panel](#the-dashboard-panel-by-panel)
5. [Budgets](#budgets)
6. [Recurring charges](#recurring-charges)
7. [Net worth](#net-worth)
8. [Transactions, filters & search](#transactions-filters--search)
9. [What to expect (and what not to)](#what-to-expect-and-what-not-to)
10. [Common gotchas](#common-gotchas)

---

## The big picture

Paisa turns raw bank activity into an accurate picture of your money. The flow is:

```
  Get transactions in  →  Categorize them  →  Read the dashboard
  (Plaid sync or import)   (rules do most of it)   (trends, budgets, net worth)
```

Everything runs locally. Your data lives in `data/paisa.db` on your machine, and
your Plaid keys live only in your local `.env`. Nothing is sent to any cloud
service except Plaid itself (to fetch your transactions).

---

## Getting your transactions in

You have two ways to add data. You can use either or both.

### Option A — Connect a bank with Plaid (recommended)

1. Go to the **Transactions** tab.
2. Click **🏦 Connect Bank**.
3. A Plaid popup opens. Search for your bank, then log in with your **real bank
   credentials** inside Plaid's secure window. Paisa never sees your bank
   password — only the transactions Plaid returns.
4. Pick the accounts to link and finish. You'll see "Connected [bank]".
5. Repeat **Connect Bank** for each institution you want (banks, credit cards,
   loans, brokerage).
6. Click **🔄 Sync** to pull transactions.

**What to expect from a sync:**
- It pulls from the **start of the current year** by default.
- The amount of history you actually get is decided by each bank — often 90 days
  to a year on the first connect. This is a Plaid/bank limit, not a Paisa bug.
- Each sync also **auto-detects transfers** between your accounts and **captures
  a net-worth snapshot** (see below).
- Re-syncing is safe — duplicates are skipped.

### Option B — Import a statement file (manual)

1. On the **Transactions** tab, click **📤 Import Statement**.
2. Drag & drop a **PDF, CSV, or Excel** statement, or click to browse.
3. Paisa detects the bank, parses the transactions, auto-categorizes, and skips
   duplicates — including if you re-upload the exact same file.

Use this for:
- History older than Plaid can reach (e.g. earlier in the year).
- Banks you'd rather not connect.
- One-off accounts.

Paisa has dedicated parsers for **Chase, Citi, PNC, and Robinhood**, plus generic
CSV/PDF handling for other banks.

---

## Categorizing & rules

Paisa auto-categorizes using **rules** — a rule is a text pattern mapped to a
category (e.g. `STARBUCKS → Dining`). Rules apply to every future import and sync.

### The Categorize tab
Lists transactions that didn't match any rule. For each, you can set a category.

### The Rules tab
- See all rules and how many transactions each has matched.
- **+ Add Rule**: enter a pattern and category. Check **"apply to existing"** to
  retroactively categorize current uncategorized transactions that match.
- Delete rules you no longer want.

### How "self-learning" actually works
- Adding a **rule** is what makes categorization stick for future transactions.
- Editing a **single transaction's** category is a one-off — it does **not**
  create a rule. If you want it to apply going forward, add a rule.

### The one habit that keeps your numbers accurate
Mark money moving **between your own accounts** as **Transfer** — credit-card
payments, brokerage transfers, moving cash from checking to savings. Otherwise
it looks like spending and inflates your expenses. Paisa auto-detects many of
these, but when a new pattern appears, categorize it as Transfer once and the
rule handles it from then on.

---

## The dashboard, panel by panel

The dashboard answers "how am I doing?" Use the **date presets** (This Month,
Last 3 Months, Year to Date, Last 12 Months, All Time) or a custom range at the
top. It defaults to **Year to Date**.

### Summary cards
- **Income** — money in, excluding transfers.
- **Expenses** — money out, excluding transfers.
- **Net Cash Flow** — income minus expenses (green positive, red negative).
- **Savings Rate** — net cash flow as a % of income.

Below the cards you may see:
- A **"transfers excluded"** note — how much inter-account movement was left out
  of the income/expense figures (so the numbers are self-explanatory).
- **Spending-spike alerts** — on single-month views, categories running well
  above their usual level are flagged (e.g. "Shopping: 6.6× your usual").

### Monthly trend
Green (income) vs red (expense) bars per month. This is where you see whether
spending is trending up or down.

### Spending donut + category breakdown
The donut shows your top categories' share of spending; the list shows amounts
and proportion bars.

### Top merchants
Your biggest merchants by spend. Store-number variants are merged (so
"WAL-MART #3400" and "WAL-MART #4185" count as one "Walmart"). Transfers are
excluded.

---

## Budgets

Set a monthly spending limit per category and track it.

1. On the dashboard **Budgets** panel, click **+ Set Budget**.
2. Pick a category and a monthly dollar limit.
3. A progress bar appears for that category:
   - **Green** — under 75% of budget
   - **Amber** — 75–100%
   - **Red** — over budget (shows how much over)

Budgets compare against the **current month's** actual spend in that category.
Income and Transfer categories aren't budgetable. Remove a budget with the ✕.

**What to expect:** budgets are informational — Paisa won't block anything, it
just shows you where you stand.

---

## Recurring charges

Paisa automatically detects **fixed recurring charges** — subscriptions, bills,
loan/mortgage payments — and lists them with an estimated monthly total.

- It looks for the **same merchant at a roughly fixed amount across several
  months**. One-off or highly variable spending (like groceries) is intentionally
  excluded.
- If a charge's amount changed over time, you'll see a **price-change flag**
  (▲ up in red, ▼ down in green), e.g. a subscription that went from $9.99 to
  $12.99.

**What to expect:** this is a heuristic. It's good at catching true recurring
bills, but a very regular habit at a steady price could occasionally show up, and
a brand-new subscription won't appear until it's recurred a few times.

---

## Net worth

Paisa snapshots your balances over time to track net worth.

- **Net worth = assets − liabilities.** Checking, savings, and brokerage balances
  are assets; credit cards, loans, and mortgages are liabilities.
- A snapshot is captured **automatically on each sync**, and you can force one
  with **Capture Now** on the Net Worth panel.
- With one snapshot you'll see the current figure; the **trend line builds over
  time** as snapshots accumulate (Plaid only provides *current* balances, not
  historical ones, so history starts from when you begin syncing).

---

## Transactions, filters & search

The **Transactions** tab is the full ledger.

- Filter by **date range, category, min/max amount**, and free-text **search**.
- Click a transaction's **category badge** to change it.
- **Select multiple** transactions and bulk-categorize them.
- The **Account** column shows which institution each transaction came from.

Note: the Transactions tab's date filter defaults to the **current month** — widen
it if you don't see older transactions.

---

## What to expect (and what not to)

**Paisa is good at:**
- Pulling and consolidating transactions across many accounts.
- Auto-categorizing recurring, common merchants.
- Showing accurate income/expense/net-worth once transfers are tagged.
- Surfacing trends, budgets, recurring bills, and spending spikes.

**Paisa does not:**
- Give financial, tax, or investment advice — it's a tracker, not an advisor.
- Move money or pay bills — it's read-only on your accounts.
- Guarantee full-year history on first connect (bank-dependent).
- Auto-sync on a schedule yet — you click **Sync** to refresh (transfer
  detection and net-worth snapshots then run automatically).

**Accuracy depends on categorization.** The single biggest driver of correct
numbers is tagging inter-account transfers as **Transfer**. Paisa automates much
of this, but review the dashboard after connecting several accounts and fix any
large "expense" that's actually a transfer or a card payment.

---

## Common gotchas

| Symptom | Cause / fix |
|---------|-------------|
| Expenses look way too high / net cash flow is very negative | Transfers between your own accounts are being counted as spending. Categorize them as **Transfer** (or re-sync to let auto-detection run). |
| "Connect Bank" is greyed out | Plaid isn't configured. Set up `.env` (see README) and restart with the venv's Python. |
| Sync only returned ~90 days | That's the bank's history limit via Plaid. Import older statements manually. |
| A charge I categorized reverted / didn't apply to others | Single-transaction edits are one-offs. Add a **rule** to apply it going forward. |
| Dashboard shows "only a few transactions" | The date filter is probably set to the current month. Use a preset like **YTD** or **All Time**. |
| Net worth shows one point only | You need multiple snapshots over time; they accumulate as you sync. |
| A recurring charge is missing | It needs to have recurred at a fairly fixed amount across a few months before detection kicks in. |

---

**Questions or issues?** See [FAQ.md](FAQ.md) and the Troubleshooting section of
[README.md](README.md).
