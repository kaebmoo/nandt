// static/js/script.js

// แปลงรูปแบบวันที่
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('th-TH', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        weekday: 'long'
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
    if (container) {
        container.insertBefore(alertDiv, container.firstChild);
    }
    // ไม่ต้องซ่อนอัตโนมัติเพื่อให้ผู้ใช้อ่านได้ตลอด
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
    
    // อย่าซ่อนการแจ้งเตือนอัตโนมัติ ให้ผู้ใช้กดปิดเอง

    // จัดการเหตุการณ์ของการเลือกวันเริ่มต้น - อัปเดตวันสิ้นสุดให้เป็นวันเดียวกันโดยอัตโนมัติ
    const startDateInput = document.getElementById('start_date');
    const endDateInput = document.getElementById('end_date');
    
    if (startDateInput && endDateInput) {
        startDateInput.addEventListener('change', function() {
            endDateInput.value = this.value;
        });
    }
    
    // สำหรับหน้าสร้างนัดหมายใหม่ - แสดง/ซ่อนตัวเลือกการนัดหมายเกิดซ้ำ
    const isRecurringCheck = document.getElementById('is_recurring');
    const recurringOptions = document.getElementById('recurring-options');
    
    if (isRecurringCheck && recurringOptions) {
        isRecurringCheck.addEventListener('change', function() {
            if (this.checked) {
                recurringOptions.style.display = 'block';
            } else {
                recurringOptions.style.display = 'none';
            }
        });
    }
    
    // จัดการการคลิกที่ปุ่มอัปเดตสถานะและปุ่มรายละเอียดในหน้ารายการนัดหมาย
    setupEventHandlers();
    
    // จัดการปุ่มค้นหาข้อมูลนัดหมายในหน้าอัปเดตสถานะ
    const fetchDetailsBtn = document.getElementById('fetch-details');
    if (fetchDetailsBtn) {
        fetchDetailsBtn.addEventListener('click', function() {
            const eventId = document.getElementById('event_id').value;
            if (eventId) {
                window.location.href = `/update_status?event_id=${eventId}`;
            } else {
                showAlert('กรุณากรอก Event ID', 'warning');
            }
        });
    }
    
    // จัดการปุ่มค้นหานัดหมายในหน้ารายการนัดหมาย
    const filterBtn = document.getElementById('filter-btn');
    if (filterBtn) {
        filterBtn.addEventListener('click', loadAppointments);
    }

    // โหลดรายการนัดหมายเมื่อโหลดหน้า (ถ้าอยู่ในหน้ารายการนัดหมาย)
    if (document.getElementById('appointments-container')) {
        loadAppointments();
    }

    // สำหรับหน้าอัปเดตสถานะ - การส่งฟอร์มอัปเดตสถานะ
    const updateStatusForm = document.querySelector('form[action*="update_status"]');
    if (updateStatusForm) {
        updateStatusForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const eventId = document.getElementById('event_id').value;
            const status = document.getElementById('status').value;
            
            if (!eventId || !status) {
                showAlert('กรุณากรอก Event ID และเลือกสถานะ', 'danger');
                return;
            }
            
            // ใช้ HTML form ที่อยู่ในหน้าเว็บโดยตรง แทนการใช้ AJAX
            // เพื่อให้แน่ใจว่าการจัดการข้อมูลทำโดย backend ซึ่งมีการตั้งค่าที่ถูกต้อง
            this.submit();
        });
    }
});

// ตั้งค่า event handlers สำหรับปุ่มต่างๆ ในหน้ารายการนัดหมาย
function setupEventHandlers() {
    // จัดการการคลิกที่ปุ่มอัปเดตสถานะ
    document.querySelectorAll('.update-status').forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const eventId = this.getAttribute('data-event-id');
            window.location.href = `/update_status?event_id=${eventId}`;
        });
    });
    
    // จัดการการคลิกที่ปุ่มดูรายละเอียด
    document.querySelectorAll('.view-details').forEach(button => {
        button.addEventListener('click', function() {
            const eventId = this.getAttribute('data-event-id');
            showEventDetails(eventId);
        });
    });
}

// แสดงรายละเอียดนัดหมายใน modal
function showEventDetails(eventId) {
    console.log("กำลังแสดงรายละเอียดสำหรับ event_id:", eventId);
    
    // แสดง loading spinner
    Swal.fire({
        title: 'กำลังโหลด...',
        text: 'กำลังโหลดข้อมูลนัดหมาย',
        allowOutsideClick: false,
        didOpen: () => {
            Swal.showLoading();
        }
    });
    
    // ดึงข้อมูลโดยตรงจาก API สำหรับกิจกรรมนี้เท่านั้น
    fetch(`/get_events?event_id=${eventId}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            Swal.close(); // ปิด loading spinner
            
            if (!data.events || data.events.length === 0) {
                Swal.fire({
                    icon: 'warning',
                    title: 'ไม่พบข้อมูล',
                    text: 'ไม่พบข้อมูลนัดหมายสำหรับ ID นี้'
                });
                return;
            }
            
            // ดึงข้อมูลนัดหมายจาก API response
            const event = data.events[0]; // ควรมีเพียงกิจกรรมเดียว
            
            // สร้าง modal แสดงรายละเอียด
            Swal.fire({
                title: 'รายละเอียดนัดหมาย',
                html: `
                    <div class="text-start">
                        <h5>${event.title}</h5>
                        <p><strong>วันที่:</strong> ${formatDate(event.start_dt.split('T')[0])}</p>
                        <p><strong>เวลา:</strong> ${event.start_dt.split('T')[1].substring(0, 5)} - ${event.end_dt.split('T')[1].substring(0, 5)}</p>
                        <p><strong>สถานที่:</strong> ${event.location || 'ไม่ระบุ'}</p>
                        <p><strong>ผู้ดูแล:</strong> ${event.who || 'ไม่ระบุ'}</p>
                        ${event.notes ? `
                        <div class="mt-3">
                            <h6>บันทึกเพิ่มเติม:</h6>
                            <div class="border p-2 rounded">
                                <pre class="mb-0" style="white-space: pre-wrap;">${event.notes}</pre>
                            </div>
                        </div>
                        ` : ''}
                        <div class="mt-3">
                            <h6>Event ID:</h6>
                            <div class="input-group">
                                <input type="text" class="form-control" value="${event.id}" readonly>
                            </div>
                        </div>
                    </div>
                `,
                width: '600px',
                showCloseButton: true,
                showCancelButton: true,
                focusConfirm: false,
                confirmButtonText: '<i class="fas fa-edit"></i> อัปเดตสถานะ',
                cancelButtonText: 'ปิด'
            }).then((result) => {
                if (result.isConfirmed) {
                    // กดปุ่มอัปเดตสถานะ
                    window.location.href = `/update_status?event_id=${event.id}`;
                }
            });
        })
        .catch(error => {
            console.error('Error fetching event details:', error);
            Swal.fire({
                icon: 'error',
                title: 'เกิดข้อผิดพลาด',
                text: 'ไม่สามารถโหลดข้อมูลนัดหมายได้: ' + error.message
            });
        });
}

// โหลดรายการนัดหมาย (สำหรับหน้ารายการนัดหมาย)
function loadAppointments() {
    const container = document.getElementById('appointments-container');
    if (!container) return;
    
    const subcalendarId = document.getElementById('subcalendar-filter') ? document.getElementById('subcalendar-filter').value : '';
    const startDate = document.getElementById('date-from') ? document.getElementById('date-from').value : '';
    const endDate = document.getElementById('date-to') ? document.getElementById('date-to').value : '';
    
    container.innerHTML = `
        <div class="text-center p-5">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">กำลังโหลด...</span>
            </div>
            <p class="mt-2">กำลังโหลดรายการนัดหมาย...</p>
        </div>
    `;
    
    // สร้าง URL พร้อมพารามิเตอร์
    let url = '/get_events';
    const params = new URLSearchParams();
    
    if (subcalendarId) params.append('subcalendar_id', subcalendarId);
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    
    if (params.toString()) {
        url += '?' + params.toString();
    }
    
    // ใช้ Fetch API สำหรับการเรียกข้อมูล
    fetch(url)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            container.innerHTML = '';
            
            if (!data.events || data.events.length === 0) {
                container.innerHTML = `
                    <div class="alert alert-info">
                        <i class="fas fa-info-circle me-2"></i>ไม่พบรายการนัดหมายในช่วงเวลาที่เลือก
                    </div>
                `;
                return;
            }
            
            // กำหนดค่า eventsData สำหรับใช้ในฟังก์ชัน showEventDetails
            window.eventsData = data.events;
            console.log("Loaded events data:", window.eventsData);
            
            // จัดกลุ่มตามวันที่
            const eventsByDate = {};
            data.events.forEach(event => {
                const startDate = event.start_dt.split('T')[0];
                if (!eventsByDate[startDate]) {
                    eventsByDate[startDate] = [];
                }
                eventsByDate[startDate].push(event);
            });
            
            // แสดงผลแยกตามวันที่
            Object.keys(eventsByDate).sort().forEach(date => {
                const dateObj = new Date(date);
                const formattedDate = dateObj.toLocaleDateString('th-TH', { 
                    weekday: 'long', 
                    year: 'numeric', 
                    month: 'long', 
                    day: 'numeric' 
                });
                
                container.innerHTML += `
                    <h4 class="mt-4 mb-3">
                        <i class="far fa-calendar-alt me-2"></i>${formattedDate}
                    </h4>
                    <div class="mb-2">
                        <span class="badge bg-primary">${eventsByDate[date].length} รายการ</span>
                    </div>
                `;
                
                eventsByDate[date].forEach(event => {
                    let statusClass = '';
                    if (event.title.includes('(มาตามนัด)')) {
                        statusClass = 'status-completed';
                    } else if (event.title.includes('(ยกเลิก)')) {
                        statusClass = 'status-cancelled';
                    } else if (event.title.includes('(ไม่มา)')) {
                        statusClass = 'status-missed';
                    }
                    
                    const startTime = event.start_dt.split('T')[1].substring(0, 5);
                    const endTime = event.end_dt.split('T')[1].substring(0, 5);
                    
                    container.innerHTML += `
                        <div class="card appointment-card ${statusClass}" data-event-id="${event.id}">
                            <div class="card-body">
                                <div class="d-flex justify-content-between">
                                    <h5 class="card-title">${event.title}</h5>
                                    <span class="badge bg-primary">${startTime} - ${endTime}</span>
                                </div>
                                <p class="card-text mb-1">
                                    <i class="fas fa-map-marker-alt me-2"></i>${event.location || 'ไม่ระบุตำแหน่ง'}
                                </p>
                                <p class="card-text">
                                    <i class="fas fa-user-md me-2"></i>${event.who || 'ไม่ระบุผู้ดูแล'}
                                </p>
                                <div class="text-end">
                                    <a href="/update_status?event_id=${event.id}" class="btn btn-sm btn-primary">
                                        <i class="fas fa-edit me-1"></i>อัปเดตสถานะ
                                    </a>
                                    <button class="btn btn-sm btn-outline-secondary view-details" data-event-id="${event.id}">
                                        <i class="fas fa-info-circle me-1"></i>รายละเอียด
                                    </button>
                                </div>
                            </div>
                        </div>
                    `;
                });
            });
            
            // ผูกเหตุการณ์ใหม่สำหรับปุ่มดูรายละเอียดที่เพิ่งสร้าง
            setupEventHandlers();
        })
        .catch(error => {
            console.error('Error loading appointments:', error);
            container.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>เกิดข้อผิดพลาดในการโหลดรายการนัดหมาย: ${error.message}
                </div>
            `;
        });
}

// สำหรับหน้าสร้างนัดหมายใหม่
document.addEventListener('DOMContentLoaded', function() {
    const newAppointmentForm = document.getElementById('new-appointment-form');
    if (newAppointmentForm) {
        newAppointmentForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            // แปลง form data เป็น URL-encoded format
            const formData = new FormData(this);
            const formParams = new URLSearchParams();
            
            for (const [key, value] of formData.entries()) {
                formParams.append(key, value);
            }
            
            fetch('/create_appointment', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: formParams.toString()
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    showAlert('สร้างนัดหมายสำเร็จ!', 'success');
                    newAppointmentForm.reset();
                    
                    // เปลี่ยนไปยังแท็บรายการนัดหมาย
                    const listTab = document.getElementById('list-tab');
                    if (listTab) {
                        const bsListTab = new bootstrap.Tab(listTab);
                        bsListTab.show();
                        
                        // โหลดรายการนัดหมายใหม่
                        loadAppointments();
                    }
                } else {
                    showAlert('เกิดข้อผิดพลาด: ' + (data.error || 'ไม่ทราบสาเหตุ'), 'danger');
                }
            })
            .catch(error => {
                console.error('Error creating appointment:', error);
                showAlert('เกิดข้อผิดพลาด: ' + error.message, 'danger');
            });
        });
    }
});