/**
 * Super Admin Panel - JavaScript Functions
 */

// Auto-dismiss alerts after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    // Auto-dismiss alerts
    const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });

    // Form validation
    const forms = document.querySelectorAll('.needs-validation');
    forms.forEach(function(form) {
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        }, false);
    });

    // Subdomain input: convert to lowercase and remove invalid characters
    const subdomainInput = document.querySelector('input[name="subdomain"]');
    if (subdomainInput) {
        subdomainInput.addEventListener('input', function(e) {
            // Convert to lowercase and remove invalid characters
            e.target.value = e.target.value
                .toLowerCase()
                .replace(/[^a-z0-9-]/g, '');
        });
    }

    // Confirm before leaving page if form has unsaved changes
    const formsWithChanges = document.querySelectorAll('form[data-confirm-leave]');
    let formChanged = false;

    formsWithChanges.forEach(function(form) {
        const originalData = new FormData(form);

        form.addEventListener('change', function() {
            formChanged = true;
        });

        form.addEventListener('submit', function() {
            formChanged = false;
        });
    });

    window.addEventListener('beforeunload', function(e) {
        if (formChanged) {
            e.preventDefault();
            e.returnValue = 'คุณมีการเปลี่ยนแปลงที่ยังไม่ได้บันทึก ต้องการออกจากหน้านี้หรือไม่?';
            return e.returnValue;
        }
    });
});

/**
 * Show loading state on button
 */
function setButtonLoading(button, loading = true) {
    if (loading) {
        button.disabled = true;
        button.classList.add('btn-loading');
        button.dataset.originalText = button.innerHTML;
        button.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>กำลังดำเนินการ...';
    } else {
        button.disabled = false;
        button.classList.remove('btn-loading');
        if (button.dataset.originalText) {
            button.innerHTML = button.dataset.originalText;
        }
    }
}

/**
 * Show confirmation modal
 */
function confirmAction(message, callback) {
    if (confirm(message)) {
        callback();
    }
}

/**
 * Format date to Thai locale
 */
function formatDateThai(dateString) {
    const date = new Date(dateString);
    const options = {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    };
    return date.toLocaleDateString('th-TH', options);
}

/**
 * Copy text to clipboard
 */
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(function() {
        showToast('คัดลอกแล้ว!', 'success');
    }, function() {
        showToast('ไม่สามารถคัดลอกได้', 'error');
    });
}

/**
 * Show toast notification (if using toast library)
 */
function showToast(message, type = 'info') {
    // Simple alert as fallback
    // Can be replaced with proper toast library like toastr.js
    const alertClass = type === 'error' ? 'danger' : type;
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${alertClass} alert-dismissible fade show position-fixed top-0 end-0 m-3`;
    alertDiv.style.zIndex = '9999';
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    document.body.appendChild(alertDiv);

    setTimeout(function() {
        alertDiv.remove();
    }, 3000);
}

/**
 * Initialize tooltips (Bootstrap)
 */
document.addEventListener('DOMContentLoaded', function() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});

/**
 * Table search/filter
 */
function initTableSearch(tableId, searchInputId) {
    const table = document.getElementById(tableId);
    const searchInput = document.getElementById(searchInputId);

    if (!table || !searchInput) return;

    searchInput.addEventListener('keyup', function() {
        const filter = searchInput.value.toLowerCase();
        const rows = table.getElementsByTagName('tr');

        for (let i = 1; i < rows.length; i++) {
            const row = rows[i];
            const text = row.textContent.toLowerCase();

            if (text.includes(filter)) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        }
    });
}

// Expose functions globally
window.setButtonLoading = setButtonLoading;
window.confirmAction = confirmAction;
window.copyToClipboard = copyToClipboard;
window.showToast = showToast;
window.initTableSearch = initTableSearch;
