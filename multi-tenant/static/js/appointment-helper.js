// multi-tenant/static/js/appointment-helper.js - Fixed Version

document.addEventListener('DOMContentLoaded', function() {
    // รอให้ NudDeeSaaSApp โหลดเสร็จก่อน
    const initializeWhenReady = () => {
        if (window.app && typeof window.app.loadAppointments === 'function') {
            // โหลดข้อมูลเริ่มต้นเมื่อ DOM โหลดเสร็จ
            window.app.loadAppointments();
            
            // ปรับแต่งฟังก์ชันดูรายละเอียดกิจกรรม
            enhanceViewDetails();
            
            // Setup filter button
            setupFilterButton();
            
            console.log('Appointment helper initialized successfully');
        } else {
            // รอ 100ms แล้วลองใหม่
            setTimeout(initializeWhenReady, 100);
        }
    };
    
    initializeWhenReady();
});

/**
 * ปรับปรุงการทำงานของปุ่มดูรายละเอียดกิจกรรม
 */
function enhanceViewDetails() {
    // ใช้ event delegation เพื่อจัดการปุ่มที่ถูกสร้างใหม่ dynamically
    document.addEventListener('click', function(event) {
        // ตรวจสอบว่า element ที่ถูกคลิกเป็นปุ่มดูรายละเอียดหรือไม่
        if (event.target.classList.contains('view-details') || 
            event.target.closest('.view-details')) {
            
            event.preventDefault();
            
            const button = event.target.classList.contains('view-details') ? 
                          event.target : event.target.closest('.view-details');
            
            const eventId = button.getAttribute('data-event-id');
            
            if (!eventId) {
                console.warn('Missing data-event-id on details button.');
                return;
            }
            
            // ตรวจสอบว่า app object และเมธอด showEventDetails พร้อมใช้งานหรือไม่
            if (window.app && typeof window.app.showEventDetails === 'function') {
                window.app.showEventDetails(eventId).catch(error => {
                    console.error('Error showing event details:', error);
                    if (window.app && typeof window.app.showNotification === 'function') {
                        window.app.showNotification('เกิดข้อผิดพลาดในการแสดงรายละเอียดกิจกรรม', 'error');
                    } else {
                        alert('เกิดข้อผิดพลาดในการแสดงรายละเอียดกิจกรรม');
                    }
                });
            } else {
                console.error('NudDeeSaaSApp (app) or showEventDetails method not found.');
                if (window.app && typeof window.app.showNotification === 'function') {
                    window.app.showNotification('ระบบแสดงรายละเอียดกิจกรรมยังไม่พร้อมใช้งาน', 'error');
                } else {
                    alert('ระบบแสดงรายละเอียดกิจกรรมยังไม่พร้อมใช้งาน');
                }
            }
        }
    });
}

/**
 * Setup filter button functionality
 */
function setupFilterButton() {
    const filterBtn = document.getElementById('filter-btn');
    if (filterBtn) {
        filterBtn.addEventListener('click', function() {
            if (window.app && typeof window.app.loadAppointments === 'function') {
                window.app.loadAppointments();
            }
        });
    }
}

// เพิ่มฟังก์ชัน global สำหรับ backward compatibility กับ script เดิม
window.loadAppointments = function() {
    if (window.app && typeof window.app.loadAppointments === 'function') {
        window.app.loadAppointments();
    } else {
        console.warn('NudDeeSaaSApp not available for loadAppointments');
    }
};

window.showEventDetails = function(eventId) {
    if (window.app && typeof window.app.showEventDetails === 'function') {
        return window.app.showEventDetails(eventId);
    } else {
        console.warn('NudDeeSaaSApp not available for showEventDetails');
        return Promise.reject(new Error('NudDeeSaaSApp not available'));
    }
};
