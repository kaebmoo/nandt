// static/js/script.js

// แปลงรูปแบบวันที่
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('th-TH', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });
}

// แปลงรูปแบบเวลา
function formatTime(timeString) {
    const [hours, minutes] = timeString.split(':');
    return `${hours}:${minutes}`;
}

// แสดงแจ้งเตือน
function showAlert(message, type = 'success') {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    // เพิ่มไว้ที่ต้นของ container
    const container = document.querySelector('.container');
    container.insertBefore(alertDiv, container.firstChild);
    
    // ซ่อนอัตโนมัติหลังจาก 5 วินาที
    setTimeout(() => {
        alertDiv.classList.remove('show');
        setTimeout(() => {
            alertDiv.remove();
        }, 500);
    }, 5000);
}

// เมื่อโหลดหน้าเสร็จ
document.addEventListener('DOMContentLoaded', function() {
    // ไฮไลท์แท็บที่กำลังเปิดอยู่
    const currentUrl = window.location.pathname;
    document.querySelectorAll('.navbar-nav .nav-link').forEach(link => {
        if (link.getAttribute('href') === currentUrl) {
            link.classList.add('active');
        }
    });
    
    // อัตโนมัติซ่อนการแจ้งเตือน
    document.querySelectorAll('.alert').forEach(alert => {
        setTimeout(() => {
            if (alert) {
                const bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            }
        }, 5000);
    });
});

// จัดการเหตุการณ์ของการเลือกวันเริ่มต้น - อัปเดตวันสิ้นสุดให้เป็นวันเดียวกันโดยอัตโนมัติ
document.addEventListener('DOMContentLoaded', function() {
    const startDateInput = document.getElementById('start_date');
    const endDateInput = document.getElementById('end_date');
    
    if (startDateInput && endDateInput) {
        startDateInput.addEventListener('change', function() {
            endDateInput.value = this.value;
        });
    }
});

// จัดการการคัดลอก Event ID
function copyEventId(eventId) {
    navigator.clipboard.writeText(eventId).then(function() {
        showAlert('คัดลอก Event ID แล้ว', 'info');
    }, function(err) {
        console.error('ไม่สามารถคัดลอก Event ID ได้:', err);
    });
}