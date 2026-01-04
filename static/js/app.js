/**
 * Lark Data Fetcher - Frontend Application
 */

// State
let appData = {
    records: [],
    orders: {},
    attachments: [],
    lastFetch: null
};

// DOM Elements
const fetchBtn = document.getElementById('fetchBtn');
const saveBtn = document.getElementById('saveBtn');
const downloadAllBtn = document.getElementById('downloadAllBtn');
const selectAllAttachments = document.getElementById('selectAllAttachments');
const downloadSelectedBtn = document.getElementById('downloadSelectedBtn');
const statusSection = document.getElementById('status');
const statusText = document.getElementById('statusText');
const statsSection = document.getElementById('stats');
const lastFetchEl = document.getElementById('lastFetch');
const recordCount = document.getElementById('recordCount');
const orderCount = document.getElementById('orderCount');
const attachmentCount = document.getElementById('attachmentCount');
const ordersContainer = document.getElementById('ordersContainer');
const recordsContainer = document.getElementById('recordsContainer');
const attachmentsContainer = document.getElementById('attachmentsContainer');
const messagesContainer = document.getElementById('messages');

// Tab functionality
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        // Update active tab button
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        // Show corresponding tab pane
        const tabId = btn.dataset.tab;
        document.querySelectorAll('.tab-pane').forEach(pane => {
            pane.classList.add('hidden');
        });
        document.getElementById(`${tabId}-tab`).classList.remove('hidden');
    });
});

// Show message notification
function showMessage(text, type = 'info') {
    const message = document.createElement('div');
    message.className = `message message-${type}`;
    message.textContent = text;
    messagesContainer.appendChild(message);

    setTimeout(() => {
        message.style.animation = 'slideIn 0.3s ease reverse';
        setTimeout(() => message.remove(), 300);
    }, 5000);
}

// Show/hide loading status
function setLoading(loading, text = 'Loading...') {
    if (loading) {
        statusSection.classList.remove('hidden');
        statusText.textContent = text;
        fetchBtn.disabled = true;
    } else {
        statusSection.classList.add('hidden');
        fetchBtn.disabled = false;
    }
}

// Update stats display
function updateStats() {
    statsSection.classList.remove('hidden');
    recordCount.textContent = appData.records.length;
    orderCount.textContent = Object.keys(appData.orders).length;
    attachmentCount.textContent = appData.attachments.length;

    if (appData.lastFetch) {
        lastFetchEl.textContent = `Last fetched: ${new Date(appData.lastFetch).toLocaleString()}`;
    }

    // Enable/disable buttons
    const hasData = appData.records.length > 0;
    saveBtn.disabled = !hasData;
    downloadAllBtn.disabled = appData.attachments.length === 0;
    selectAllAttachments.disabled = appData.attachments.length === 0;
}

// Format field value for display
function formatFieldValue(value) {
    if (value === null || value === undefined) {
        return '-';
    }

    if (Array.isArray(value)) {
        // Check if it's an attachment array
        if (value.length > 0 && value[0].file_token) {
            return `📎 ${value.length} attachment(s)`;
        }
        // Check if it's a link/user array
        if (value.length > 0 && value[0].text) {
            return value.map(v => v.text).join(', ');
        }
        return value.map(v => formatFieldValue(v)).join(', ');
    }

    if (typeof value === 'object') {
        if (value.text) return value.text;
        if (value.name) return value.name;
        return JSON.stringify(value);
    }

    return String(value);
}

// Get file icon based on type
function getFileIcon(type) {
    const icons = {
        'image': '🖼️',
        'pdf': '📄',
        'doc': '📝',
        'xls': '📊',
        'zip': '📦',
        'video': '🎬',
        'audio': '🎵'
    };

    const typeLower = (type || '').toLowerCase();
    for (const [key, icon] of Object.entries(icons)) {
        if (typeLower.includes(key)) return icon;
    }
    return '📎';
}

// Format file size
function formatFileSize(bytes) {
    if (!bytes) return 'Unknown size';
    const units = ['B', 'KB', 'MB', 'GB'];
    let size = bytes;
    let unitIndex = 0;

    while (size >= 1024 && unitIndex < units.length - 1) {
        size /= 1024;
        unitIndex++;
    }

    return `${size.toFixed(1)} ${units[unitIndex]}`;
}

// Render orders
function renderOrders() {
    if (Object.keys(appData.orders).length === 0) {
        ordersContainer.innerHTML = '<p class="empty-message">No processing orders found.</p>';
        return;
    }

    ordersContainer.innerHTML = Object.entries(appData.orders).map(([orderId, records]) => `
        <div class="order-card">
            <div class="order-header" onclick="toggleOrderRecords('${orderId}')">
                <span class="order-id">📦 Order: ${orderId}</span>
                <span class="order-count">${records.length} record(s)</span>
            </div>
            <div class="order-records" id="order-${orderId}">
                ${records.map(record => renderRecordCard(record)).join('')}
            </div>
        </div>
    `).join('');
}

// Toggle order records visibility
window.toggleOrderRecords = function(orderId) {
    const recordsDiv = document.getElementById(`order-${orderId}`);
    recordsDiv.classList.toggle('expanded');
};

// Render a single record card
function renderRecordCard(record) {
    const fields = record.fields || {};
    const fieldEntries = Object.entries(fields).slice(0, 10); // Limit displayed fields

    return `
        <div class="record-card">
            <div class="record-id">Record ID: ${record.record_id || 'N/A'}</div>
            <div class="record-fields">
                ${fieldEntries.map(([name, value]) => `
                    <div class="field">
                        <div class="field-name">${name}</div>
                        <div class="field-value">${formatFieldValue(value)}</div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

// Render all records
function renderRecords() {
    if (appData.records.length === 0) {
        recordsContainer.innerHTML = '<p class="empty-message">No records loaded.</p>';
        return;
    }

    recordsContainer.innerHTML = appData.records.map(record => renderRecordCard(record)).join('');
}

// Render attachments
function renderAttachments() {
    if (appData.attachments.length === 0) {
        attachmentsContainer.innerHTML = '<p class="empty-message">No attachments found in the records.</p>';
        return;
    }

    attachmentsContainer.innerHTML = appData.attachments.map((att, index) => `
        <div class="attachment-card">
            <input type="checkbox" class="attachment-checkbox" data-index="${index}" data-token="${att.file_token}">
            <span class="attachment-icon">${getFileIcon(att.type)}</span>
            <div class="attachment-info">
                <div class="attachment-name">${att.name}</div>
                <div class="attachment-meta">${formatFileSize(att.size)} • ${att.field_name}</div>
            </div>
            <button class="attachment-download" onclick="downloadSingleAttachment('${att.file_token}', '${att.name.replace(/'/g, "\\'")}')">
                Download
            </button>
        </div>
    `).join('');
}

// Render all data
function renderData() {
    renderOrders();
    renderRecords();
    renderAttachments();
    updateStats();
}

// Fetch data from Lark
async function fetchData() {
    setLoading(true, 'Fetching data from Lark Base...');

    try {
        const response = await fetch('/api/fetch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const result = await response.json();

        if (!result.success) {
            throw new Error(result.error || 'Failed to fetch data');
        }

        // Get the full data
        const dataResponse = await fetch('/api/data');
        const dataResult = await dataResponse.json();

        if (dataResult.success) {
            appData = dataResult.data;
            renderData();
            showMessage(`Fetched ${result.stats.total_records} records from ${result.stats.total_orders} orders`, 'success');
        }

    } catch (error) {
        console.error('Fetch error:', error);
        showMessage(`Error: ${error.message}`, 'error');
    } finally {
        setLoading(false);
    }
}

// Save data to JSON
async function saveData() {
    setLoading(true, 'Saving data to JSON files...');

    try {
        const response = await fetch('/api/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const result = await response.json();

        if (!result.success) {
            throw new Error(result.error || 'Failed to save data');
        }

        showMessage('Data saved successfully!', 'success');

    } catch (error) {
        console.error('Save error:', error);
        showMessage(`Error: ${error.message}`, 'error');
    } finally {
        setLoading(false);
    }
}

// Download all attachments
async function downloadAllAttachments() {
    if (appData.attachments.length === 0) {
        showMessage('No attachments to download', 'error');
        return;
    }

    setLoading(true, `Downloading ${appData.attachments.length} attachments...`);

    try {
        const response = await fetch('/api/attachments/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ all: true })
        });

        const result = await response.json();

        if (!result.success) {
            throw new Error(result.error || 'Failed to download attachments');
        }

        showMessage(`Downloaded ${result.stats.success} files (${result.stats.errors} errors)`,
            result.stats.errors > 0 ? 'info' : 'success');

    } catch (error) {
        console.error('Download error:', error);
        showMessage(`Error: ${error.message}`, 'error');
    } finally {
        setLoading(false);
    }
}

// Download selected attachments
async function downloadSelectedAttachments() {
    const checkboxes = document.querySelectorAll('.attachment-checkbox:checked');
    const fileTokens = Array.from(checkboxes).map(cb => cb.dataset.token);

    if (fileTokens.length === 0) {
        showMessage('No attachments selected', 'error');
        return;
    }

    setLoading(true, `Downloading ${fileTokens.length} selected attachments...`);

    try {
        const response = await fetch('/api/attachments/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_tokens: fileTokens })
        });

        const result = await response.json();

        if (!result.success) {
            throw new Error(result.error || 'Failed to download attachments');
        }

        showMessage(`Downloaded ${result.stats.success} files (${result.stats.errors} errors)`,
            result.stats.errors > 0 ? 'info' : 'success');

    } catch (error) {
        console.error('Download error:', error);
        showMessage(`Error: ${error.message}`, 'error');
    } finally {
        setLoading(false);
    }
}

// Download single attachment
window.downloadSingleAttachment = async function(fileToken, filename) {
    showMessage(`Downloading ${filename}...`, 'info');

    try {
        const response = await fetch(`/api/attachments/download/${fileToken}`);

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Download failed');
        }

        // Create download link
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();

        showMessage(`Downloaded: ${filename}`, 'success');

    } catch (error) {
        console.error('Download error:', error);
        showMessage(`Error: ${error.message}`, 'error');
    }
};

// Select all attachments toggle
function toggleSelectAllAttachments() {
    const checkboxes = document.querySelectorAll('.attachment-checkbox');
    const allChecked = Array.from(checkboxes).every(cb => cb.checked);

    checkboxes.forEach(cb => {
        cb.checked = !allChecked;
    });

    updateDownloadSelectedButton();
}

// Update download selected button state
function updateDownloadSelectedButton() {
    const checkedCount = document.querySelectorAll('.attachment-checkbox:checked').length;
    downloadSelectedBtn.disabled = checkedCount === 0;
    downloadSelectedBtn.textContent = checkedCount > 0
        ? `Download Selected (${checkedCount})`
        : 'Download Selected';
}

// Event Listeners
fetchBtn.addEventListener('click', fetchData);
saveBtn.addEventListener('click', saveData);
downloadAllBtn.addEventListener('click', downloadAllAttachments);
selectAllAttachments.addEventListener('click', toggleSelectAllAttachments);
downloadSelectedBtn.addEventListener('click', downloadSelectedAttachments);

// Delegate checkbox change events
attachmentsContainer.addEventListener('change', (e) => {
    if (e.target.classList.contains('attachment-checkbox')) {
        updateDownloadSelectedButton();
    }
});

// Load initial data on page load
document.addEventListener('DOMContentLoaded', async () => {
    try {
        const response = await fetch('/api/data');
        const result = await response.json();

        if (result.success && result.data.records.length > 0) {
            appData = result.data;
            renderData();
        }
    } catch (error) {
        console.log('No cached data available');
    }
});
