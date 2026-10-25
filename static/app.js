// Paisa - Personal Finance Tracker JavaScript

// ==================== STATE ====================
let categories = [];
let selectedTransactions = new Set();
let currentCategoryCallback = null;

// ==================== INITIALIZATION ====================
document.addEventListener('DOMContentLoaded', async () => {
    // Set up tab navigation
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });
    
    // Set default dates (current month)
    const today = new Date();
    const firstOfMonth = new Date(today.getFullYear(), today.getMonth(), 1);
    const lastOfMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0);

    // Dashboard defaults to Year-to-Date (more useful than a single month).
    const firstOfYear = new Date(today.getFullYear(), 0, 1);
    document.getElementById('dash-start-date').value = formatDate(firstOfYear);
    document.getElementById('dash-end-date').value = formatDate(today);

    // Transactions filter keeps the current-month default.
    document.getElementById('filter-start').value = formatDate(firstOfMonth);
    document.getElementById('filter-end').value = formatDate(lastOfMonth);
    
    // Load categories first
    await loadCategories();
    
    // Load initial data
    loadDashboard();
    loadTransactions();
    loadRules();
    loadUncategorized();
    
    // Set up file upload
    setupFileUpload();
});

function formatDate(date) {
    return date.toISOString().split('T')[0];
}

function formatCurrency(amount) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(amount);
}

// ==================== TAB NAVIGATION ====================
function switchTab(tabId) {
    // Update tab buttons
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`[data-tab="${tabId}"]`).classList.add('active');
    
    // Update content
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');
    
    // Refresh data for the tab
    if (tabId === 'dashboard') loadDashboard();
    else if (tabId === 'transactions') loadTransactions();
    else if (tabId === 'categorize') loadUncategorized();
    else if (tabId === 'rules') loadRules();
}

// ==================== CATEGORIES ====================
async function loadCategories() {
    try {
        const response = await fetch('/api/categories');
        const data = await response.json();
        
        if (data.success) {
            categories = data.categories;
            populateCategoryDropdowns();
            populateCategoryPicker();
        }
    } catch (error) {
        console.error('Error loading categories:', error);
    }
}

function populateCategoryDropdowns() {
    const selects = [
        document.getElementById('filter-category'),
        document.getElementById('bulk-category'),
        document.getElementById('rule-category')
    ];
    
    selects.forEach(select => {
        if (!select) return;
        
        const firstOption = select.options[0];
        select.innerHTML = '';
        if (firstOption) select.appendChild(firstOption);
        
        categories.forEach(cat => {
            const option = document.createElement('option');
            option.value = cat.name;
            option.textContent = `${cat.icon} ${cat.name}`;
            select.appendChild(option);
        });
    });
}

function populateCategoryPicker() {
    const picker = document.getElementById('category-picker');
    picker.innerHTML = '';
    
    categories.forEach(cat => {
        const item = document.createElement('div');
        item.className = 'category-picker-item';
        item.innerHTML = `<span>${cat.icon}</span><span>${cat.name}</span>`;
        item.onclick = () => selectCategory(cat.name);
        picker.appendChild(item);
    });
}

function getCategoryIcon(categoryName) {
    const cat = categories.find(c => c.name === categoryName);
    return cat ? cat.icon : '❓';
}

function getCategoryColor(categoryName) {
    const cat = categories.find(c => c.name === categoryName);
    return cat ? cat.color : '#9ca3af';
}

// ==================== DASHBOARD ====================
async function loadDashboard() {
    const startDate = document.getElementById('dash-start-date').value;
    const endDate = document.getElementById('dash-end-date').value;
    
    try {
        // Load summary
        const summaryUrl = new URL('/api/summary', window.location.origin);
        if (startDate) summaryUrl.searchParams.set('start_date', startDate);
        if (endDate) summaryUrl.searchParams.set('end_date', endDate);
        
        const summaryResponse = await fetch(summaryUrl);
        const summary = await summaryResponse.json();
        
        if (summary.success) {
            document.getElementById('total-income').textContent = formatCurrency(summary.total_income);
            document.getElementById('total-expenses').textContent = formatCurrency(summary.total_expenses);
            
            const netEl = document.getElementById('net-cashflow');
            netEl.textContent = formatCurrency(summary.net_cash_flow);
            netEl.className = 'card-value ' + (summary.net_cash_flow >= 0 ? 'positive' : 'negative');
            
            document.getElementById('savings-rate').textContent = `${summary.savings_rate}%`;

            renderSummaryExtras(summary);

            // Render category breakdown
            renderCategoryBreakdown(summary.categories, summary.total_expenses);
        }
        
        // Load top merchants
        const merchantUrl = new URL('/api/merchants', window.location.origin);
        if (startDate) merchantUrl.searchParams.set('start_date', startDate);
        if (endDate) merchantUrl.searchParams.set('end_date', endDate);
        
        const merchantResponse = await fetch(merchantUrl);
        const merchantData = await merchantResponse.json();
        
        if (merchantData.success) {
            renderMerchants(merchantData.merchants);
        }

        // Load monthly trend (independent of the date filter; shows last 12 months)
        loadTrend();

        // Load account balances (only shows if there are linked accounts)
        loadAccounts();

        // Load budgets (current month)
        loadBudgets();

        // Load recurring charges
        loadRecurring();

        // Load net worth history
        loadNetWorth();

    } catch (error) {
        console.error('Error loading dashboard:', error);
    }
}

// ==================== NET WORTH ====================
async function loadNetWorth() {
    const panel = document.getElementById('networth-panel');
    try {
        const res = await fetch('/api/networth');
        const data = await res.json();
        if (!data.success || !data.history || data.history.length === 0) {
            if (panel) panel.style.display = 'none';
            return;
        }
        if (panel) panel.style.display = '';
        renderNetWorth(data.history);
    } catch (error) {
        console.error('Error loading net worth:', error);
        if (panel) panel.style.display = 'none';
    }
}

async function captureNetWorth() {
    const res = await fetch('/api/networth/capture', { method: 'POST' });
    const data = await res.json();
    if (data.success) loadNetWorth();
}

// Line chart of net worth over snapshot dates (single point shows as a dot + label).
function renderNetWorth(history) {
    const el = document.getElementById('networth-chart');
    const cur = document.getElementById('networth-current');
    if (!el) return;

    const latest = history[history.length - 1];
    if (cur) cur.textContent = `— ${formatCurrency(latest.net_worth)} (assets ${fmtShort(latest.assets)} − debts ${fmtShort(latest.liabilities)})`;

    if (history.length === 1) {
        el.innerHTML = `<p style="color:var(--text-secondary); padding:1.5rem; text-align:center;">
            Net worth: <strong style="color:#10b981;">${formatCurrency(latest.net_worth)}</strong><br>
            <span style="font-size:0.8rem;">One snapshot so far. The trend line builds as you sync over time.</span></p>`;
        return;
    }

    const W = Math.max(history.length * 80, 320), H = 220;
    const pad = { top: 16, right: 16, bottom: 36, left: 60 };
    const plotW = W - pad.left - pad.right, plotH = H - pad.top - pad.bottom;
    const vals = history.map(h => h.net_worth);
    const min = Math.min(...vals, 0), max = Math.max(...vals);
    const range = (max - min) || 1;
    const x = i => pad.left + (history.length === 1 ? plotW / 2 : (i / (history.length - 1)) * plotW);
    const y = v => pad.top + plotH - ((v - min) / range) * plotH;

    let pts = history.map((h, i) => `${x(i)},${y(h.net_worth)}`).join(' ');
    let dots = history.map((h, i) => `<circle cx="${x(i)}" cy="${y(h.net_worth)}" r="3" fill="#6366f1"><title>${h.date}: ${fmt(h.net_worth)}</title></circle>`).join('');
    let labels = history.map((h, i) => `<text x="${x(i)}" y="${H-16}" text-anchor="middle" font-size="10" fill="#94a3b8">${h.date.slice(5)}</text>`).join('');

    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}">
        <polyline points="${pts}" fill="none" stroke="#6366f1" stroke-width="2"/>
        ${dots}${labels}
        <text x="${pad.left-8}" y="${y(max)+4}" text-anchor="end" font-size="10" fill="#94a3b8">${fmtShort(max)}</text>
        <text x="${pad.left-8}" y="${y(min)+4}" text-anchor="end" font-size="10" fill="#94a3b8">${fmtShort(min)}</text>
    </svg>`;
}

// ==================== RECURRING ====================
async function loadRecurring() {
    const panel = document.getElementById('recurring-panel');
    try {
        const res = await fetch('/api/recurring');
        const data = await res.json();
        if (!data.success || !data.recurring || data.recurring.length === 0) {
            if (panel) panel.style.display = 'none';
            return;
        }
        if (panel) panel.style.display = '';
        const totalEl = document.getElementById('recurring-total');
        if (totalEl) totalEl.textContent = `— ~${formatCurrency(data.estimated_monthly_total)}/mo`;

        const list = document.getElementById('recurring-list');
        list.innerHTML = data.recurring.map(r => {
            let flag = '';
            if (r.price_change) {
                const arrow = r.price_change.direction === 'up' ? '▲' : '▼';
                const color = r.price_change.direction === 'up' ? '#ef4444' : '#10b981';
                flag = `<span class="recurring-flag" style="color:${color};" title="Price ${r.price_change.direction}">`
                     + `${arrow} ${formatCurrency(r.price_change.from)}→${formatCurrency(r.price_change.to)}</span>`;
            }
            return `<div class="recurring-item">
                        <span class="recurring-merchant">${r.merchant}</span>
                        <span class="recurring-meta">${r.occurrences}× · last ${r.last_date}</span>
                        ${flag}
                        <span class="recurring-amt">${formatCurrency(r.typical_amount)}</span>
                    </div>`;
        }).join('');
    } catch (error) {
        console.error('Error loading recurring:', error);
        if (panel) panel.style.display = 'none';
    }
}

// Transfers-excluded note + anomaly flags under the summary cards.
function renderSummaryExtras(summary) {
    const el = document.getElementById('summary-extras');
    if (!el) return;
    let html = '';

    if (summary.transfers_excluded && summary.transfers_excluded > 0) {
        html += `<div class="summary-note">↔ ${formatCurrency(summary.transfers_excluded)} in transfers excluded from income & expenses</div>`;
    }

    if (summary.anomalies && summary.anomalies.length > 0) {
        const items = summary.anomalies.map(a =>
            `<li><strong>${a.category}</strong>: ${formatCurrency(a.amount)} — about ${a.ratio}× your usual ${formatCurrency(a.typical)}</li>`
        ).join('');
        html += `<div class="anomaly-banner">
                    <span class="anomaly-title">⚠ Spending spikes this period</span>
                    <ul>${items}</ul>
                 </div>`;
    }

    el.innerHTML = html;
}

// ==================== BUDGETS ====================
async function loadBudgets() {
    try {
        const res = await fetch('/api/budgets');
        const data = await res.json();
        if (data.success) renderBudgets(data);
    } catch (error) {
        console.error('Error loading budgets:', error);
    }
}

function renderBudgets(data) {
    const list = document.getElementById('budget-list');
    const monthEl = document.getElementById('budget-month');
    if (!list) return;

    const names = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    if (monthEl) monthEl.textContent = `— ${names[data.month]} ${data.year}`;

    if (!data.budgets || data.budgets.length === 0) {
        list.innerHTML = '<p style="color: var(--text-secondary); padding: 1rem 0;">No budgets set. Click "Set Budget" to add one.</p>';
        return;
    }

    list.innerHTML = data.budgets.map(b => {
        const pct = Math.min(b.pct_used, 100);
        let barColor = '#10b981';          // green under 75%
        if (b.over_budget) barColor = '#ef4444';   // red over budget
        else if (b.pct_used >= 75) barColor = '#f59e0b'; // amber nearing
        const remainLabel = b.over_budget
            ? `<span style="color:#ef4444;">${formatCurrency(Math.abs(b.remaining))} over</span>`
            : `${formatCurrency(b.remaining)} left`;
        return `
            <div class="budget-item">
                <div class="budget-row">
                    <span class="budget-cat">${getCategoryIcon(b.category)} ${b.category}</span>
                    <span class="budget-nums">${formatCurrency(b.spent)} / ${formatCurrency(b.monthly_limit)}</span>
                </div>
                <div class="budget-bar"><div class="budget-bar-fill" style="width:${pct}%; background:${barColor};"></div></div>
                <div class="budget-foot">
                    <span>${b.pct_used}% used</span>
                    <span>${remainLabel}</span>
                    <button class="budget-del" title="Remove budget" onclick="deleteBudget('${b.category}')">✕</button>
                </div>
            </div>`;
    }).join('');
}

function showBudgetModal() {
    // populate category dropdown
    const sel = document.getElementById('budget-category');
    sel.innerHTML = '';
    categories.filter(c => c.name !== 'Transfer' && c.name !== 'Income').forEach(c => {
        const o = document.createElement('option');
        o.value = c.name;
        o.textContent = `${c.icon} ${c.name}`;
        sel.appendChild(o);
    });
    document.getElementById('budget-limit').value = '';
    document.getElementById('budget-modal').classList.add('active');
}

function hideBudgetModal() {
    document.getElementById('budget-modal').classList.remove('active');
}

async function saveBudget() {
    const category = document.getElementById('budget-category').value;
    const limit = parseFloat(document.getElementById('budget-limit').value);
    if (!category || isNaN(limit) || limit < 0) {
        alert('Pick a category and enter a valid limit.');
        return;
    }
    const res = await fetch('/api/budgets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category, monthly_limit: limit }),
    });
    const data = await res.json();
    if (data.success) {
        hideBudgetModal();
        loadBudgets();
    } else {
        alert(data.error || 'Failed to save budget');
    }
}

async function deleteBudget(category) {
    const res = await fetch(`/api/budgets/${encodeURIComponent(category)}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.success) loadBudgets();
}

async function loadAccounts() {
    const panel = document.getElementById('accounts-panel');
    try {
        const res = await fetch('/api/plaid/accounts');
        const data = await res.json();
        if (!data.success || !data.institutions || data.institutions.length === 0) {
            if (panel) panel.style.display = 'none';
            return;
        }
        if (panel) panel.style.display = '';
        renderAccounts(data.institutions);
    } catch (error) {
        console.error('Error loading accounts:', error);
        if (panel) panel.style.display = 'none';
    }
}

function renderAccounts(institutions) {
    const el = document.getElementById('accounts-list');
    if (!el) return;

    // grand total across all institutions (sum of current balances)
    const grand = institutions.reduce((s, inst) => s + (inst.total_balance || 0), 0);

    el.innerHTML = institutions.map(inst => {
        const rows = inst.accounts.map(a => {
            const mask = a.mask ? ` ••${a.mask}` : '';
            const bal = a.current_balance != null ? formatCurrency(a.current_balance) : '—';
            return `<div class="account-row">
                        <span class="account-name">${a.name || a.type || 'Account'}${mask}</span>
                        <span class="account-bal">${bal}</span>
                    </div>`;
        }).join('');
        return `<div class="institution-group">
                    <div class="institution-head">
                        <span>${inst.institution}</span>
                        <span class="institution-total">${formatCurrency(inst.total_balance || 0)}</span>
                    </div>
                    ${rows}
                </div>`;
    }).join('') +
    `<div class="accounts-grand"><span>Total across accounts</span><span>${formatCurrency(grand)}</span></div>`;
}

// Apply a date-range preset to the dashboard and reload.
function applyPreset(preset) {
    const today = new Date();
    let start, end = today;

    switch (preset) {
        case 'month':
            start = new Date(today.getFullYear(), today.getMonth(), 1);
            end = new Date(today.getFullYear(), today.getMonth() + 1, 0);
            break;
        case '3m':
            start = new Date(today.getFullYear(), today.getMonth() - 2, 1);
            break;
        case 'ytd':
            start = new Date(today.getFullYear(), 0, 1);
            break;
        case '12m':
            start = new Date(today.getFullYear(), today.getMonth() - 11, 1);
            break;
        case 'all':
            start = new Date(2000, 0, 1); // effectively unbounded
            break;
        default:
            start = new Date(today.getFullYear(), 0, 1);
    }

    document.getElementById('dash-start-date').value = formatDate(start);
    document.getElementById('dash-end-date').value = formatDate(end);

    // highlight the active preset button
    document.querySelectorAll('.preset-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.preset === preset);
    });

    loadDashboard();
}

async function loadTrend() {
    try {
        const res = await fetch('/api/trend?months=12');
        const data = await res.json();
        if (data.success) renderTrendChart(data.trend);
    } catch (error) {
        console.error('Error loading trend:', error);
    }
}

// Render an SVG grouped bar chart: income vs expenses per month. No libraries.
function renderTrendChart(trend) {
    const container = document.getElementById('trend-chart');
    if (!container) return;

    if (!trend || trend.length === 0) {
        container.innerHTML = '<p style="color: var(--text-secondary); text-align:center; padding:2rem;">Not enough data yet for a trend.</p>';
        return;
    }

    const W = Math.max(trend.length * 70, 300);
    const H = 240;
    const pad = { top: 16, right: 12, bottom: 40, left: 56 };
    const plotW = W - pad.left - pad.right;
    const plotH = H - pad.top - pad.bottom;

    const maxVal = Math.max(1, ...trend.map(m => Math.max(m.income, m.expenses)));
    // "nice" round max for the axis
    const niceMax = niceCeil(maxVal);
    const y = v => pad.top + plotH - (v / niceMax) * plotH;

    const groupW = plotW / trend.length;
    const barW = Math.min(18, groupW / 3);

    let bars = '';
    let labels = '';
    trend.forEach((m, i) => {
        const gx = pad.left + i * groupW + groupW / 2;
        const incX = gx - barW - 1;
        const expX = gx + 1;
        bars += `<rect x="${incX}" y="${y(m.income)}" width="${barW}" height="${pad.top + plotH - y(m.income)}" fill="#10b981" rx="2">`
             +  `<title>${m.month} income ${fmt(m.income)}</title></rect>`;
        bars += `<rect x="${expX}" y="${y(m.expenses)}" width="${barW}" height="${pad.top + plotH - y(m.expenses)}" fill="#ef4444" rx="2">`
             +  `<title>${m.month} expenses ${fmt(m.expenses)}</title></rect>`;
        // month label like "Oct"
        const label = monthShort(m.month);
        labels += `<text x="${gx}" y="${H - 20}" text-anchor="middle" font-size="11" fill="#94a3b8">${label}</text>`;
    });

    // y-axis gridlines + labels (0, 25, 50, 75, 100%)
    let grid = '';
    for (let t = 0; t <= 4; t++) {
        const val = niceMax * t / 4;
        const yy = y(val);
        grid += `<line x1="${pad.left}" y1="${yy}" x2="${W - pad.right}" y2="${yy}" stroke="#334155" stroke-width="1" stroke-dasharray="3 3"/>`;
        grid += `<text x="${pad.left - 8}" y="${yy + 4}" text-anchor="end" font-size="10" fill="#94a3b8">${fmtShort(val)}</text>`;
    }

    container.innerHTML =
        `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" preserveAspectRatio="xMidYMid meet">${grid}${bars}${labels}</svg>`;
}

function niceCeil(v) {
    const pow = Math.pow(10, Math.floor(Math.log10(v)));
    return Math.ceil(v / pow) * pow;
}
function fmt(v) { return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v); }
function fmtShort(v) {
    if (v >= 1000) return '$' + (v / 1000).toFixed(v % 1000 === 0 ? 0 : 1) + 'k';
    return '$' + Math.round(v);
}
function monthShort(ym) {
    const [y, m] = ym.split('-');
    const names = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return `${names[parseInt(m, 10)]} ${y.slice(2)}`;
}

function renderCategoryBreakdown(categoryData, totalExpenses) {
    const list = document.getElementById('category-list');
    list.innerHTML = '';

    renderCategoryDonut(categoryData, totalExpenses);

    if (!categoryData || categoryData.length === 0) {
        list.innerHTML = '<p style="color: var(--text-secondary); text-align: center; padding: 2rem;">No expense data yet. Import a statement to get started.</p>';
        return;
    }
    
    categoryData.forEach(cat => {
        const percentage = totalExpenses > 0 ? (cat.amount / totalExpenses * 100) : 0;
        const color = getCategoryColor(cat.name);
        
        const item = document.createElement('div');
        item.className = 'category-item';
        item.innerHTML = `
            <span class="category-icon">${getCategoryIcon(cat.name)}</span>
            <div style="flex: 1;">
                <div style="display: flex; justify-content: space-between;">
                    <span class="category-name">${cat.name}</span>
                    <span class="category-amount">${formatCurrency(cat.amount)}</span>
                </div>
                <div class="category-bar">
                    <div class="category-bar-fill" style="width: ${percentage}%; background: ${color};"></div>
                </div>
            </div>
        `;
        list.appendChild(item);
    });
}

// SVG donut chart of spending share by category (top 7 + "Other").
function renderCategoryDonut(categoryData, totalExpenses) {
    const el = document.getElementById('category-donut');
    if (!el) return;
    if (!categoryData || categoryData.length === 0 || !totalExpenses) {
        el.innerHTML = '';
        return;
    }

    // Take top 7 categories, bucket the rest into "Other"
    const sorted = [...categoryData].sort((a, b) => b.amount - a.amount);
    const top = sorted.slice(0, 7);
    const restTotal = sorted.slice(7).reduce((s, c) => s + c.amount, 0);
    const slices = top.map(c => ({ name: c.name, amount: c.amount, color: getCategoryColor(c.name) }));
    if (restTotal > 0) slices.push({ name: 'Other categories', amount: restTotal, color: '#64748b' });

    const total = slices.reduce((s, c) => s + c.amount, 0);
    if (total <= 0) { el.innerHTML = ''; return; }

    const size = 180, r = 70, cx = size / 2, cy = size / 2, stroke = 28;
    const circ = 2 * Math.PI * r;
    let offset = 0;
    let segments = '';
    slices.forEach(s => {
        const frac = s.amount / total;
        const len = frac * circ;
        segments += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${s.color}" stroke-width="${stroke}" `
                 +  `stroke-dasharray="${len} ${circ - len}" stroke-dashoffset="${-offset}" transform="rotate(-90 ${cx} ${cy})">`
                 +  `<title>${s.name}: ${formatCurrency(s.amount)} (${(frac*100).toFixed(1)}%)</title></circle>`;
        offset += len;
    });

    const legend = slices.map(s =>
        `<div class="donut-legend-item"><span class="donut-swatch" style="background:${s.color}"></span>`
        + `${s.name} <span class="donut-pct">${(s.amount/total*100).toFixed(0)}%</span></div>`
    ).join('');

    el.innerHTML =
        `<div class="donut-wrap">
            <svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">
                ${segments}
                <text x="${cx}" y="${cy-4}" text-anchor="middle" font-size="12" fill="#94a3b8">Total</text>
                <text x="${cx}" y="${cy+14}" text-anchor="middle" font-size="14" fill="#e2e8f0" font-weight="600">${fmtShort(total)}</text>
            </svg>
            <div class="donut-legend">${legend}</div>
        </div>`;
}

function renderMerchants(merchants) {
    const list = document.getElementById('merchant-list');
    list.innerHTML = '';
    
    if (!merchants || merchants.length === 0) {
        list.innerHTML = '<p style="color: var(--text-secondary); text-align: center; padding: 2rem;">No transaction data yet.</p>';
        return;
    }
    
    merchants.forEach((merchant, i) => {
        const item = document.createElement('div');
        item.className = 'merchant-item';
        item.innerHTML = `
            <span style="color: var(--text-secondary); width: 24px;">${i + 1}.</span>
            <span class="merchant-name">${merchant.name}</span>
            <span class="merchant-amount">${formatCurrency(merchant.amount)}</span>
        `;
        list.appendChild(item);
    });
}

// ==================== TRANSACTIONS ====================
async function loadTransactions() {
    const params = new URLSearchParams();
    
    const search = document.getElementById('search-input').value;
    const startDate = document.getElementById('filter-start').value;
    const endDate = document.getElementById('filter-end').value;
    const category = document.getElementById('filter-category').value;
    const minAmount = document.getElementById('filter-min').value;
    const maxAmount = document.getElementById('filter-max').value;
    
    if (search) params.set('search', search);
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    if (category) params.set('category', category);
    if (minAmount) params.set('min_amount', minAmount);
    if (maxAmount) params.set('max_amount', maxAmount);
    
    try {
        const response = await fetch(`/api/transactions?${params}`);
        const data = await response.json();
        
        if (data.success) {
            renderTransactions(data.transactions);
        }
    } catch (error) {
        console.error('Error loading transactions:', error);
    }
}

function renderTransactions(transactions) {
    const tbody = document.getElementById('transactions-body');
    tbody.innerHTML = '';
    
    selectedTransactions.clear();
    updateBulkActions();
    
    if (!transactions || transactions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 2rem; color: var(--text-secondary);">No transactions found. Import a statement to get started.</td></tr>';
        return;
    }
    
    transactions.forEach(tx => {
        const row = document.createElement('tr');
        const isDebit = tx.transaction_type === 'debit';
        
        row.innerHTML = `
            <td><input type="checkbox" data-id="${tx.id}" onchange="toggleSelection('${tx.id}')" /></td>
            <td>${new Date(tx.date).toLocaleDateString()}</td>
            <td>
                <div>${tx.description}</div>
                ${tx.original_description && tx.original_description !== tx.description ? 
                    `<div style="font-size: 0.8rem; color: var(--text-secondary);">${tx.original_description}</div>` : ''}
            </td>
            <td>
                <span class="category-badge" onclick="showCategoryPicker('${tx.id}')">
                    ${getCategoryIcon(tx.category)} ${tx.category}
                </span>
            </td>
            <td class="${isDebit ? 'amount-debit' : 'amount-credit'}">
                ${isDebit ? '-' : '+'}${formatCurrency(tx.amount)}
            </td>
            <td style="color: var(--text-secondary);">${tx.institution}</td>
        `;
        tbody.appendChild(row);
    });
}

function clearFilters() {
    document.getElementById('search-input').value = '';
    document.getElementById('filter-category').value = '';
    document.getElementById('filter-min').value = '';
    document.getElementById('filter-max').value = '';
    
    const today = new Date();
    const firstOfMonth = new Date(today.getFullYear(), today.getMonth(), 1);
    const lastOfMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0);
    document.getElementById('filter-start').value = formatDate(firstOfMonth);
    document.getElementById('filter-end').value = formatDate(lastOfMonth);
    
    loadTransactions();
}

function toggleSelectAll() {
    const selectAll = document.getElementById('select-all').checked;
    document.querySelectorAll('#transactions-body input[type="checkbox"]').forEach(cb => {
        cb.checked = selectAll;
        const id = cb.dataset.id;
        if (selectAll) {
            selectedTransactions.add(id);
        } else {
            selectedTransactions.delete(id);
        }
    });
    updateBulkActions();
}

function toggleSelection(id) {
    if (selectedTransactions.has(id)) {
        selectedTransactions.delete(id);
    } else {
        selectedTransactions.add(id);
    }
    updateBulkActions();
}

function updateBulkActions() {
    const bulkActions = document.getElementById('bulk-actions');
    const count = selectedTransactions.size;
    
    if (count > 0) {
        bulkActions.style.display = 'flex';
        document.getElementById('selected-count').textContent = `${count} selected`;
    } else {
        bulkActions.style.display = 'none';
    }
}

async function bulkCategorize() {
    const category = document.getElementById('bulk-category').value;
    if (!category) {
        alert('Please select a category');
        return;
    }
    
    try {
        const response = await fetch('/api/transactions/bulk-categorize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                transaction_ids: Array.from(selectedTransactions),
                category: category
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            selectedTransactions.clear();
            document.getElementById('select-all').checked = false;
            loadTransactions();
        }
    } catch (error) {
        console.error('Error bulk categorizing:', error);
    }
}

// ==================== CATEGORY PICKER ====================
function showCategoryPicker(txId) {
    currentCategoryCallback = async (category) => {
        try {
            const response = await fetch(`/api/transactions/${txId}/category`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ category })
            });
            
            if (response.ok) {
                loadTransactions();
                loadDashboard();
            }
        } catch (error) {
            console.error('Error updating category:', error);
        }
    };
    
    document.getElementById('category-modal').classList.add('show');
}

function selectCategory(category) {
    if (currentCategoryCallback) {
        currentCategoryCallback(category);
        currentCategoryCallback = null;
    }
    hideCategoryModal();
}

function hideCategoryModal() {
    document.getElementById('category-modal').classList.remove('show');
}

// ==================== UNCATEGORIZED ====================
async function loadUncategorized() {
    try {
        const response = await fetch('/api/uncategorized?limit=50');
        const data = await response.json();
        
        if (data.success) {
            document.getElementById('uncategorized-count').textContent = data.count;
            renderUncategorized(data.transactions);
        }
    } catch (error) {
        console.error('Error loading uncategorized:', error);
    }
}

function renderUncategorized(items) {
    const list = document.getElementById('uncategorized-list');
    list.innerHTML = '';
    
    if (!items || items.length === 0) {
        list.innerHTML = '<div style="text-align: center; padding: 3rem; color: var(--text-secondary);">🎉 All transactions are categorized!</div>';
        return;
    }
    
    items.forEach(item => {
        const tx = item.transaction;
        const suggestion = item.suggested_pattern;
        const isDebit = tx.transaction_type === 'debit';
        
        const div = document.createElement('div');
        div.className = 'uncategorized-item';
        div.innerHTML = `
            <div class="tx-details">
                <div class="tx-description">${tx.description}</div>
                <div class="tx-meta">
                    ${new Date(tx.date).toLocaleDateString()} • ${tx.institution}
                    ${suggestion ? `<br>Suggested pattern: <code>${suggestion}</code>` : ''}
                </div>
            </div>
            <div class="tx-amount ${isDebit ? 'amount-debit' : 'amount-credit'}">
                ${isDebit ? '-' : '+'}${formatCurrency(tx.amount)}
            </div>
            <div class="tx-actions">
                <button class="btn btn-secondary btn-sm" onclick="showQuickCategorize('${tx.id}', '${suggestion || ''}')">
                    Categorize
                </button>
            </div>
        `;
        list.appendChild(div);
    });
}

function showQuickCategorize(txId, suggestedPattern) {
    currentCategoryCallback = async (category) => {
        try {
            // Update the transaction category
            await fetch(`/api/transactions/${txId}/category`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ category })
            });
            
            // If there's a suggested pattern, offer to create a rule
            if (suggestedPattern && confirm(`Create a rule to auto-categorize future "${suggestedPattern}" transactions as "${category}"?`)) {
                await fetch('/api/rules', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        pattern: suggestedPattern,
                        category: category,
                        apply_existing: true
                    })
                });
            }
            
            loadUncategorized();
            loadRules();
            loadDashboard();
            
        } catch (error) {
            console.error('Error categorizing:', error);
        }
    };
    
    document.getElementById('category-modal').classList.add('show');
}

// ==================== RULES ====================
async function loadRules() {
    try {
        const response = await fetch('/api/rules');
        const data = await response.json();
        
        if (data.success) {
            renderRules(data.rules);
        }
    } catch (error) {
        console.error('Error loading rules:', error);
    }
}

function renderRules(rules) {
    const list = document.getElementById('rules-list');
    list.innerHTML = '';
    
    if (!rules || rules.length === 0) {
        list.innerHTML = '<div style="text-align: center; padding: 3rem; color: var(--text-secondary);">No custom rules yet. Rules are created when you categorize transactions.</div>';
        return;
    }
    
    rules.forEach(rule => {
        const div = document.createElement('div');
        div.className = 'rule-item';
        div.innerHTML = `
            <div>
                <span class="rule-pattern">${rule.pattern}</span>
                <span class="rule-arrow">→</span>
                <span class="category-badge">
                    ${getCategoryIcon(rule.category)} ${rule.category}
                </span>
                <span class="rule-match-count">(${rule.match_count} matches)</span>
            </div>
            <button class="btn btn-ghost btn-sm" onclick="deleteRule(${rule.id})">🗑️</button>
        `;
        list.appendChild(div);
    });
}

function showAddRuleModal() {
    document.getElementById('rule-pattern').value = '';
    document.getElementById('rule-category').value = '';
    document.getElementById('rule-apply-existing').checked = true;
    document.getElementById('rule-modal').classList.add('show');
}

function hideRuleModal() {
    document.getElementById('rule-modal').classList.remove('show');
}

async function saveRule() {
    const pattern = document.getElementById('rule-pattern').value.trim();
    const category = document.getElementById('rule-category').value;
    const applyExisting = document.getElementById('rule-apply-existing').checked;
    
    if (!pattern || !category) {
        alert('Please enter a pattern and select a category');
        return;
    }
    
    try {
        const response = await fetch('/api/rules', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                pattern,
                category,
                apply_existing: applyExisting
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            hideRuleModal();
            loadRules();
            loadUncategorized();
            loadTransactions();
            
            if (data.applied_to > 0) {
                alert(`Rule created and applied to ${data.applied_to} existing transactions.`);
            }
        }
    } catch (error) {
        console.error('Error saving rule:', error);
    }
}

async function deleteRule(ruleId) {
    if (!confirm('Delete this rule? Existing categorizations will not be changed.')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/rules/${ruleId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadRules();
        }
    } catch (error) {
        console.error('Error deleting rule:', error);
    }
}

// ==================== FILE UPLOAD ====================
function setupFileUpload() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    
    // Drag and drop
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });
    
    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });
    
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            uploadFile(files[0]);
        }
    });
    
    // Click to upload
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            uploadFile(fileInput.files[0]);
        }
    });
}

async function uploadFile(file) {
    const status = document.getElementById('upload-status');
    status.className = 'upload-status loading';
    status.textContent = `Uploading ${file.name}...`;
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.success) {
            status.className = 'upload-status success';
            status.innerHTML = `
                ✅ ${data.message}<br>
                <small>Institution: ${data.institution} | Total parsed: ${data.total_parsed} | Duplicates: ${data.duplicate_count}</small>
            `;
            
            // Refresh data
            setTimeout(() => {
                hideUploadModal();
                loadDashboard();
                loadTransactions();
                loadUncategorized();
            }, 2000);
            
        } else {
            status.className = 'upload-status error';
            status.textContent = `❌ ${data.error}`;
        }
        
    } catch (error) {
        status.className = 'upload-status error';
        status.textContent = `❌ Upload failed: ${error.message}`;
    }
}

function showUploadModal() {
    document.getElementById('upload-status').className = 'upload-status';
    document.getElementById('file-input').value = '';
    document.getElementById('upload-modal').classList.add('show');
}

function hideUploadModal() {
    document.getElementById('upload-modal').classList.remove('show');
}

// ==================== MODAL HANDLING ====================
// Close modals when clicking outside
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal')) {
        e.target.classList.remove('show');
    }
});

// Close modals with Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal.show').forEach(m => m.classList.remove('show'));
    }
});
