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
    
    document.getElementById('dash-start-date').value = formatDate(firstOfMonth);
    document.getElementById('dash-end-date').value = formatDate(lastOfMonth);
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
        
    } catch (error) {
        console.error('Error loading dashboard:', error);
    }
}

function renderCategoryBreakdown(categoryData, totalExpenses) {
    const list = document.getElementById('category-list');
    list.innerHTML = '';
    
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
