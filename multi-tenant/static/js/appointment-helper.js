// static/js/appointment-helper.js - Enhanced and Corrected

document.addEventListener('DOMContentLoaded', function() {
    // โหลดข้อมูลเริ่มต้นเมื่อ DOM โหลดเสร็จ
    // ตรวจสอบให้แน่ใจว่า app object (NudDeeSaaSApp instance) พร้อมใช้งานแล้ว
    // app object ถูกสร้างและกำหนดให้ window.app ใน script.js
    if (window.app) {
        // เรียกใช้เมธอด loadAppointments จาก instance ของ NudDeeSaaSApp
        window.app.loadAppointments();
    } else {
        console.warn('NudDeeSaaSApp (app) not yet initialized. Cannot load initial events from appointment-helper.js.');
        // สามารถเพิ่ม fallback notification ได้หากต้องการ แต่ควรจัดการที่ script.js เป็นหลัก
    }
    
    // ปรับแต่งฟังก์ชันดูรายละเอียดกิจกรรม
    enhanceViewDetails();
});

/**
 * ปรับปรุงการทำงานของปุ่มดูรายละเอียดกิจกรรม (details-btn)
 * ให้เรียกใช้เมธอด showEventDetails ของ NudDeeSaaSApp
 */
function enhanceViewDetails() {
    // หาทุก element ที่มีคลาส 'details-btn'
    const detailsButtons = document.querySelectorAll('.details-btn');
    
    detailsButtons.forEach(button => {
        button.addEventListener('click', async function(e) { // เพิ่ม async เนื่องจาก showEventDetails อาจเป็น async
            e.preventDefault(); // ป้องกันการทำงานเริ่มต้นของลิงก์
            
            const eventId = this.getAttribute('data-event-id');
            if (!eventId) {
                console.warn('Missing data-event-id on details button.');
                return;
            }
            
            // ตรวจสอบว่า app object และเมธอด showEventDetails พร้อมใช้งานหรือไม่
            if (window.app && typeof window.app.showEventDetails === 'function') {
                try {
                    // เรียกใช้เมธอด showEventDetails จาก instance ของ NudDeeSaaSApp
                    await window.app.showEventDetails(eventId);
                } catch (error) {
                    console.error('Error calling app.showEventDetails:', error);
                    // ใช้ Notification System ของแอปพลิเคชันแทน alert()
                    if (window.app && typeof window.app.showNotification === 'function') {
                        window.app.showNotification('เกิดข้อผิดพลาดในการแสดงรายละเอียดกิจกรรม', 'error');
                    } else {
                        // Fallback alert หาก Notification System ยังไม่พร้อม
                        alert('เกิดข้อผิดพลาดในการแสดงรายละเอียดกิจกรรม');
                    }
                }
            } else {
                console.error('NudDeeSaaSApp (app) or showEventDetails method not found. Cannot display event details.');
                // ใช้ Notification System ของแอปพลิเคชันแทน alert()
                if (window.app && typeof window.app.showNotification === 'function') {
                    window.app.showNotification('ระบบแสดงรายละเอียดกิจกรรมยังไม่พร้อมใช้งาน', 'error');
                } else {
                    alert('ระบบแสดงรายละเอียดกิจกรรมยังไม่พร้อมใช้งาน');
                }
            }
        });
    });
}
