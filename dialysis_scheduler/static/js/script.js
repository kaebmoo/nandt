// dialysis_scheduler/static/js/script.js

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
            this.submit();
        });
    }


    // จัดการฟอร์มสร้างนัดหมายใหม่ (สำหรับทั้ง single และ recurring)
    // จัดการฟอร์มสร้างนัดหมายใหม่ (Hybrid Approach - แก้ไข form token)
    const newAppointmentForm = document.getElementById('new-appointment-form');
    if (newAppointmentForm) {
        let isSubmitting = false;
        
        // ลบ event listener เก่าทั้งหมด
        newAppointmentForm.onsubmit = null;
        
        newAppointmentForm.addEventListener('submit', function(e) {
            // ป้องกันการ submit แบب browser default
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
            
            console.log('Form submitted via JavaScript - preventing default');
            
            // ป้องกันการส่งซ้ำ
            if (isSubmitting) {
                console.log('Form is already being submitted');
                return false;
            }
            
            // ล้าง error messages เก่า
            document.querySelectorAll('.field-error').forEach(el => el.textContent = '');
            document.querySelectorAll('.form-control, .form-select').forEach(el => {
                el.classList.remove('is-invalid', 'is-valid');
            });
            
            isSubmitting = true;
            
            // ปิดการใช้งานปุ่มส่ง
            const submitButton = this.querySelector('button[type="submit"]');
            const originalButtonText = submitButton.innerHTML;
            submitButton.disabled = true;
            submitButton.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>กำลังบันทึก...';
            
            // ส่งข้อมูลด้วย FormData
            const formData = new FormData(this);
            
            fetch('/create_appointment', {  // ใช้ URL โดยตรง
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // แสดงข้อความสำเร็จ
                    const isRecurring = document.getElementById('is_recurring').checked;
                    if (isRecurring) {
                        showAlert('สร้างนัดหมายเกิดซ้ำสำเร็จ!', 'success');
                    } else {
                        showAlert('สร้างนัดหมายสำเร็จ!', 'success');
                    }
                    
                    // รีเซ็ตฟอร์ม
                    this.reset();
                    
                    // ซ่อน recurring options
                    const recurringOptions = document.getElementById('recurring-options');
                    if (recurringOptions) {
                        recurringOptions.style.display = 'none';
                    }
                    
                    // สร้าง form token ใหม่
                    updateFormToken();
                    
                    // เปลี่ยนไปยังแท็บรายการนัดหมาย
                    const listTab = document.getElementById('list-tab');
                    if (listTab) {
                        const bsListTab = new bootstrap.Tab(listTab);
                        bsListTab.show();
                        
                        // โหลดรายการนัดหมายใหม่
                        setTimeout(() => {
                            if (typeof loadAppointments === 'function') {
                                loadAppointments();
                            } else if (typeof window.loadAppointments === 'function') {
                                window.loadAppointments();
                            }
                        }, 1000);
                    }
                } else {
                    // แสดง error messages
                    showAlert(data.error || 'เกิดข้อผิดพลาดในการบันทึก', 'danger');
                    
                    // อัปเดต form token ใหม่
                    if (data.new_form_token) {
                        updateFormToken(data.new_form_token);
                    }
                    
                    // แสดง field errors
                    if (data.field_errors) {
                        for (const [field, error] of Object.entries(data.field_errors)) {
                            const errorElement = document.getElementById(`${field}-error`);
                            if (errorElement) {
                                errorElement.textContent = error;
                            }
                            
                            // เพิ่มคลาส is-invalid
                            const inputElement = document.querySelector(`[name="${field}"]`);
                            if (inputElement) {
                                inputElement.classList.add('is-invalid');
                            }
                        }
                    }
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showAlert('เกิดข้อผิดพลาดในการเชื่อมต่อ: ' + error.message, 'danger');
                
                // สร้าง form token ใหม่เมื่อเกิด error
                updateFormToken();
            })
            .finally(() => {
                // รีเซ็ตสถานะ
                isSubmitting = false;
                submitButton.disabled = false;
                submitButton.innerHTML = originalButtonText;
            });
            
            return false; // ป้องกันการ submit เพิ่มเติม
        }, true); // ใช้ capture phase
    }

    // ฟังก์ชันอัปเดต form token
    function updateFormToken(newToken = null) {
        const formTokenField = document.querySelector('input[name="form_token"]');
        if (formTokenField) {
            if (newToken) {
                formTokenField.value = newToken;
                console.log('Form token updated:', newToken);
            } else {
                formTokenField.value = generateUUID();
                console.log('New form token generated:', formTokenField.value);
            }
        }
    }

    // ฟังก์ชันสร้าง UUID สำหรับ form token
    function generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            const r = Math.random() * 16 | 0;
            const v = c == 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }

    // ฟังก์ชันล้าง validation errors เมื่อผู้ใช้เริ่มแก้ไข
    document.addEventListener('DOMContentLoaded', function() {
        const formFields = document.querySelectorAll('#new-appointment-form input, #new-appointment-form select, #new-appointment-form textarea');
        
        formFields.forEach(field => {
            field.addEventListener('input', function() {
                // ล้าง error message
                const errorElement = document.getElementById(`${this.name}-error`);
                if (errorElement) {
                    errorElement.textContent = '';
                }
                
                // ลบคลาส is-invalid
                this.classList.remove('is-invalid');
                this.classList.add('is-valid');
            });
            
            field.addEventListener('change', function() {
                // ล้าง error message
                const errorElement = document.getElementById(`${this.name}-error`);
                if (errorElement) {
                    errorElement.textContent = '';
                }
                
                // ลบคลาส is-invalid
                this.classList.remove('is-invalid');
                this.classList.add('is-valid');
            });
        });
    });
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
// แสดงรายละเอียดนัดหมายใน modal
function showEventDetails(eventId) {
    console.log("กำลังแสดงรายละเอียดสำหรับ event_id:", eventId);
    
    // แสดง loading spinner
    if (typeof Swal !== 'undefined') {
        Swal.fire({
            title: 'กำลังโหลด...',
            text: 'กำลังโหลดข้อมูลนัดหมาย',
            allowOutsideClick: false,
            didOpen: () => {
                Swal.showLoading();
            }
        });
    }
    
    // ดึงข้อมูลโดยตรงจาก API สำหรับกิจกรรมนี้เท่านั้น
    fetch(`/get_events?event_id=${eventId}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (typeof Swal !== 'undefined') {
                Swal.close(); // ปิด loading spinner
            }
            
            if (!data.events || data.events.length === 0) {
                if (typeof Swal !== 'undefined') {
                    Swal.fire({
                        icon: 'warning',
                        title: 'ไม่พบข้อมูล',
                        text: 'ไม่พบข้อมูลนัดหมายสำหรับ ID นี้'
                    });
                } else {
                    alert('ไม่พบข้อมูลนัดหมายสำหรับ ID นี้');
                }
                return;
            }
            
            // ดึงข้อมูลนัดหมายจาก API response
            const event = data.events[0]; // ควรมีเพียงกิจกรรมเดียว
            const subcalendarDisplay = event.subcalendar_display || 'ไม่ระบุปฏิทิน';
            
            // สร้าง modal แสดงรายละเอียด
            if (typeof Swal !== 'undefined') {
                Swal.fire({
                    title: 'รายละเอียดนัดหมาย',
                    html: `
                        <div class="text-start">
                            <h5>${event.title}</h5>
                            <div class="mb-3">
                                <span class="badge bg-secondary">
                                    <i class="fas fa-calendar me-1"></i>${subcalendarDisplay}
                                </span>
                            </div>
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
            } else {
                // Fallback สำหรับกรณีที่ไม่มี SweetAlert2
                const details = `
                    ${event.title}
                    ปฏิทิน: ${subcalendarDisplay}
                    วันที่: ${formatDate(event.start_dt.split('T')[0])}
                    เวลา: ${event.start_dt.split('T')[1].substring(0, 5)} - ${event.end_dt.split('T')[1].substring(0, 5)}
                    สถานที่: ${event.location || 'ไม่ระบุ'}
                    ผู้ดูแล: ${event.who || 'ไม่ระบุ'}
                    Event ID: ${event.id}
                    ${event.notes ? `\nบันทึก: ${event.notes}` : ''}
                `;
                
                if (confirm(details + '\n\nต้องการอัปเดตสถานะหรือไม่?')) {
                    window.location.href = `/update_status?event_id=${event.id}`;
                }
            }
        })
        .catch(error => {
            console.error('Error fetching event details:', error);
            if (typeof Swal !== 'undefined') {
                Swal.fire({
                    icon: 'error',
                    title: 'เกิดข้อผิดพลาด',
                    text: 'ไม่สามารถโหลดข้อมูลนัดหมายได้: ' + error.message
                });
            } else {
                alert('ไม่สามารถโหลดข้อมูลนัดหมายได้: ' + error.message);
            }
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
    
    console.log('Loading appointments from:', url); // Debug
    
    // ใช้ Fetch API สำหรับการเรียกข้อมูล
    fetch(url)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Received data:', data); // Debug
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
                    
                    // เพิ่มการแสดงชื่อปฏิทินย่อย
                    const subcalendarDisplay = event.subcalendar_display || 'ไม่ระบุปฏิทิน';
                    
                    container.innerHTML += `
                        <div class="card appointment-card ${statusClass}" data-event-id="${event.id}">
                            <div class="card-body">
                                <div class="d-flex justify-content-between align-items-start mb-2">
                                    <div class="flex-grow-1">
                                        <h5 class="card-title mb-1">${event.title}</h5>
                                        <div class="mb-2">
                                            <span class="badge bg-secondary me-2">
                                                <i class="fas fa-calendar me-1"></i>${subcalendarDisplay}
                                            </span>
                                            <span class="badge bg-primary">
                                                <i class="fas fa-clock me-1"></i>${startTime} - ${endTime}
                                            </span>
                                        </div>
                                    </div>
                                </div>
                                <div class="row">
                                    <div class="col-md-6">
                                        <p class="card-text mb-1">
                                            <i class="fas fa-map-marker-alt me-2 text-muted"></i>
                                            <small>${event.location || 'ไม่ระบุตำแหน่ง'}</small>
                                        </p>
                                    </div>
                                    <div class="col-md-6">
                                        <p class="card-text mb-1">
                                            <i class="fas fa-user-md me-2 text-muted"></i>
                                            <small>${event.who || 'ไม่ระบุผู้ดูแล'}</small>
                                        </p>
                                    </div>
                                </div>
                                <div class="text-end mt-2">
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