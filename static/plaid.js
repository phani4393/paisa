// Paisa - Plaid integration (bank connect + sync)

// ==================== INIT ====================
document.addEventListener('DOMContentLoaded', () => {
    refreshPlaidStatus();
});

// Show Plaid status: whether it's configured, and any linked accounts.
async function refreshPlaidStatus() {
    try {
        const res = await fetch('/api/plaid/status');
        const data = await res.json();

        const connectBtn = document.getElementById('connect-bank-btn');
        const syncBtn = document.getElementById('sync-btn');

        if (!data.configured) {
            // Plaid not set up — disable connect button with a hint
            if (connectBtn) {
                connectBtn.disabled = true;
                connectBtn.title = 'Set PLAID_CLIENT_ID and PLAID_SECRET in your .env file';
            }
            renderLinkedAccounts([]);
            return;
        }

        if (connectBtn) {
            connectBtn.disabled = false;
            connectBtn.title = '';
        }

        const accounts = data.linked_accounts || [];
        renderLinkedAccounts(accounts);

        // Show the Sync button only when at least one account is linked
        if (syncBtn) {
            syncBtn.style.display = accounts.length > 0 ? '' : 'none';
        }
    } catch (err) {
        console.error('Failed to load Plaid status:', err);
    }
}

function renderLinkedAccounts(accounts) {
    const container = document.getElementById('linked-accounts');
    if (!container) return;

    if (!accounts.length) {
        container.innerHTML = '';
        return;
    }

    container.innerHTML = accounts.map(acct => {
        const mask = acct.account_mask ? ` ••${acct.account_mask}` : '';
        const synced = acct.last_synced
            ? `Last synced: ${new Date(acct.last_synced).toLocaleString()}`
            : 'Not synced yet';
        return `
            <div class="linked-account">
                <div class="linked-account-info">
                    <span class="linked-account-bank">🏦 ${escapeHtml(acct.institution_name || 'Bank')}</span>
                    <span class="linked-account-name">${escapeHtml(acct.account_name || 'Account')}${mask}</span>
                    <span class="linked-account-synced">${synced}</span>
                </div>
                <button class="btn btn-ghost btn-sm" onclick="unlinkAccount('${acct.account_id}')">Unlink</button>
            </div>
        `;
    }).join('');
}

// ==================== CONNECT BANK (PLAID LINK) ====================
async function connectBank() {
    const statusEl = document.getElementById('plaid-status');
    setStatus(statusEl, 'Opening bank connection...', 'info');

    try {
        // 1. Get a link token from our backend
        const res = await fetch('/api/plaid/create-link-token', { method: 'POST' });
        const data = await res.json();

        if (!data.success) {
            setStatus(statusEl, data.error || 'Could not start bank connection', 'error');
            return;
        }

        // 2. Initialize Plaid Link with the token
        const handler = Plaid.create({
            token: data.link_token,
            onSuccess: async (publicToken, metadata) => {
                setStatus(statusEl, 'Linking account...', 'info');
                await exchangeToken(publicToken, statusEl);
            },
            onExit: (err, metadata) => {
                if (err) {
                    setStatus(statusEl, `Connection cancelled: ${err.display_message || err.error_message || ''}`, 'error');
                } else {
                    setStatus(statusEl, '', '');
                }
            },
        });

        handler.open();
    } catch (err) {
        setStatus(statusEl, `Error: ${err.message}`, 'error');
    }
}

// Exchange the public token for an access token (server-side) and persist accounts.
async function exchangeToken(publicToken, statusEl) {
    try {
        const res = await fetch('/api/plaid/exchange-token', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ public_token: publicToken }),
        });
        const data = await res.json();

        if (data.success) {
            setStatus(statusEl, `✅ Connected ${escapeHtml(data.institution)} (${data.accounts_linked} account(s)). Click Sync to import transactions.`, 'success');
            await refreshPlaidStatus();
        } else {
            setStatus(statusEl, data.error || 'Failed to link account', 'error');
        }
    } catch (err) {
        setStatus(statusEl, `Error: ${err.message}`, 'error');
    }
}

// ==================== SYNC ====================
async function syncPlaid() {
    const statusEl = document.getElementById('plaid-status');
    const syncBtn = document.getElementById('sync-btn');

    if (syncBtn) syncBtn.disabled = true;
    setStatus(statusEl, '🔄 Syncing this year\u2019s transactions from your banks (this can take a moment)...', 'info');

    try {
        // No date args => backend defaults to start of the current year (YTD backfill).
        const res = await fetch('/api/plaid/sync', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        });
        const data = await res.json();

        if (data.success) {
            let msg = `✅ Synced ${data.new_count} new transaction(s)`;
            if (data.duplicate_count) msg += `, skipped ${data.duplicate_count} duplicate(s)`;
            if (data.errors && data.errors.length) {
                msg += `. Some accounts had errors: ${data.errors.join('; ')}`;
            }
            setStatus(statusEl, msg, data.errors && data.errors.length ? 'error' : 'success');

            // Refresh the rest of the dashboard/transactions if those helpers exist
            if (typeof loadTransactions === 'function') loadTransactions();
            if (typeof loadDashboard === 'function') loadDashboard();
            if (typeof loadUncategorized === 'function') loadUncategorized();
            await refreshPlaidStatus();
        } else {
            setStatus(statusEl, data.error || 'Sync failed', 'error');
        }
    } catch (err) {
        setStatus(statusEl, `Error: ${err.message}`, 'error');
    } finally {
        if (syncBtn) syncBtn.disabled = false;
    }
}

// ==================== UNLINK ====================
async function unlinkAccount(accountId) {
    if (!confirm('Unlink this account? Already-imported transactions will stay, but it will stop syncing.')) {
        return;
    }

    try {
        const res = await fetch(`/api/plaid/unlink/${accountId}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
            await refreshPlaidStatus();
        }
    } catch (err) {
        console.error('Failed to unlink:', err);
    }
}

// ==================== HELPERS ====================
function setStatus(el, message, type) {
    if (!el) return;
    el.textContent = message;
    el.className = 'upload-status' + (type ? ` ${type}` : '');
}

function escapeHtml(str) {
    if (str == null) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}
