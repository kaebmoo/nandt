// appointment-helper.js
document.addEventListener('DOMContentLoaded', function() {
    // โหลดข้อมูลอัตโนมัติเมื่อเข้าหน้า
    loadInitialEvents();
    
    // ปรับแต่งฟังก์ชันดูรายละเอียด
    enhanceViewDetails();
});

function loadInitialEvents() {
    // ตรวจสอบว่ามีฟังก์ชัน loadEvents หรือไม่
    if (typeof loadEvents === 'function') {
        // เรียกฟังก์ชัน loadEvents ที่มีอยู่แล้ว
        loadEvents();
    } else {
        console.log('ไม่พบฟังก์ชัน loadEvents');
    }
}

function enhanceViewDetails() {
    // หาทุก element ที่มีคลาส 'details-btn' และผูกกับฟังก์ชันใหม่
    const detailsButtons = document.querySelectorAll('.details-btn');
    
    detailsButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            
            const eventId = this.getAttribute('data-event-id');
            if (!eventId) return;
            
            // ใช้ API เพื่อดึงข้อมูลกิจกรรมโดยตรง
            fetch(`/get_events?event_id=${eventId}`)
                .then(response => response.json())
                .then(data => {
                    if (data.events && data.events.length > 0) {
                        // ถ้ามีฟังก์ชันสำหรับแสดงรายละเอียด ให้เรียกใช้
                        if (typeof showEventDetails === 'function') {
                            showEventDetails(data.events[0]);
                        } else if (typeof viewEventDetails === 'function') {
                            // หรือถ้ามีฟังก์ชัน viewEventDetails อยู่แล้ว
                            viewEventDetails(eventId);
                        } else {
                            console.log('ไม่พบฟังก์ชันสำหรับแสดงรายละเอียดกิจกรรม');
                        }
                    } else {
                        alert('ไม่พบข้อมูลกิจกรรม');
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('เกิดข้อผิดพลาดในการดึงข้อมูลกิจกรรม');
                });
        });
    });
}