// multi-tenant/static/js/script.js - Complete Version with All Missing Methods

class NudDeeSaaSApp {
    constructor() {
        this.config = {
            debug: window.DEBUG || false,
            apiBaseUrl: window.API_BASE_URL || '',
            csrfToken: this.getCSRFToken(),
            retryAttempts: 3,
            retryDelay: 1000
        };
        
        this.state = {
            currentUser: null,
            currentOrganization: null,
            eventsCache: new Map(),
            formTokens: new Set(),
            toastMixin: null,
            // เพิ่มสำหรับป้องกัน double submit
            submittingForms: new Set(),
            lastRequestTimes: new Map(),
            requestFingerprints: new Map()
        };
        
        this.eventHandlers = new Map();
        this.init();
    }
    
    init() {
        try {
            this.setupSweetAlert2();
            this.loadUserContext();
            this.setupEventListeners();
            this.initializeComponents();
            this.setupErrorHandling();
            this.startHeartbeat();
            
            if (typeof moment !== 'undefined') {
                moment.locale('th');
            }

            this.log('info', 'NudDee SaaS App initialized successfully');
        } catch (error) {
            this.log('error', 'Failed to initialize app:', error);
            this.showNotification('เกิดข้อผิดพลาดในการเริ่มต้นระบบ', 'error');
        }
    }

    // === Double Submit Prevention Methods ===
    generateRequestFingerprint(data) {
        const keyData = {
            email: data.email || '',
            organization_name: data.organization_name || '',
            contact_email: data.contact_email || '',
            title: data.title || '',
            start_date: data.start_date || '',
            start_time: data.start_time || ''
        };
        const dataString = JSON.stringify(keyData, Object.keys(keyData).sort());
        let hash = 0;
        for (let i = 0; i < dataString.length; i++) {
            const char = dataString.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash;
        }
        return hash.toString(36);
    }

    checkRapidRequest(fingerprint, minimumInterval = 2000) {
        const lastTime = this.state.lastRequestTimes.get(fingerprint);
        const now = Date.now();
        if (lastTime && (now - lastTime) < minimumInterval) {
            return false;
        }
        this.state.lastRequestTimes.set(fingerprint, now);
        return true;
    }
    
    initializeDoubleClickPrevention() {
        document.addEventListener('click', (event) => {
            const button = event.target.closest('button[type="submit"], .submit-btn');
            if (!button) return;

            const lastClick = button.dataset.lastClickTime;
            const now = Date.now();
            
            if (lastClick && (now - parseInt(lastClick)) < 2000) {
                event.preventDefault();
                event.stopPropagation();
                this.log('warn', 'Double click prevented on button:', button);
                this.showNotification('กรุณารอสักครู่ก่อนคลิกอีกครั้ง', 'warning');
                return false;
            }
            button.dataset.lastClickTime = now.toString();
        }, true);
    }

    setupDateTimeAutoCorrection() {
        const startDateInput = document.querySelector('input[name="start_date"]');
        const startTimeInput = document.querySelector('input[name="start_time"]');
        const endDateInput = document.querySelector('input[name="end_date"]');
        const endTimeInput = document.querySelector('input[name="end_time"]');
        
        if (!startDateInput || !startTimeInput || !endDateInput || !endTimeInput) {
            this.log('debug', 'Date/time inputs not found for auto-correction');
            return;
        }
        
        const autoCorrectEndTime = () => {
            try {
                if (!startDateInput.value || !startTimeInput.value) return;
                
                const startDateTime = new Date(startDateInput.value + 'T' + startTimeInput.value);
                
                // ถ้ายังไม่ได้ตั้งค่า end date ให้ตั้งเป็นวันเดียวกัน
                if (!endDateInput.value) {
                    endDateInput.value = startDateInput.value;
                }
                
                // ถ้ายังไม่ได้ตั้งค่า end time หรือ end time น้อยกว่า start time
                if (!endTimeInput.value) {
                    const endDateTime = new Date(startDateTime.getTime() + (60 * 60 * 1000)); // เพิ่ม 1 ชั่วโมง
                    endTimeInput.value = endDateTime.toTimeString().substr(0, 5);
                    this.showNotification('ตั้งเวลาสิ้นสุดเป็น ' + endTimeInput.value + ' อัตโนมัติ', 'info');
                } else {
                    const endDateTime = new Date(endDateInput.value + 'T' + endTimeInput.value);
                    if (endDateTime <= startDateTime) {
                        const correctedEndTime = new Date(startDateTime.getTime() + (60 * 60 * 1000));
                        endDateInput.value = correctedEndTime.toISOString().split('T')[0];
                        endTimeInput.value = correctedEndTime.toTimeString().substr(0, 5);
                        this.showNotification('ปรับเวลาสิ้นสุดเป็น ' + endTimeInput.value + ' อัตโนมัติ', 'info');
                    }
                }
            } catch (error) {
                this.log('error', 'Error in auto-correct:', error);
            }
        };
        
        // เพิ่ม event listeners
        startDateInput.addEventListener('change', autoCorrectEndTime);
        startTimeInput.addEventListener('change', autoCorrectEndTime);
        endDateInput.addEventListener('change', () => {
            // ตรวจสอบว่า end date ไม่เป็นวันก่อน start date
            if (startDateInput.value && endDateInput.value) {
                if (new Date(endDateInput.value) < new Date(startDateInput.value)) {
                    endDateInput.value = startDateInput.value;
                    autoCorrectEndTime();
                }
            }
        });
        
        // ตั้งค่าเริ่มต้น
        this.setDefaultDateTime();
        
        this.log('debug', 'Date/time auto-correction setup completed');
    }

    setDefaultDateTime() {
        const startDateInput = document.querySelector('input[name="start_date"]');
        const startTimeInput = document.querySelector('input[name="start_time"]');
        
        if (startDateInput && !startDateInput.value) {
            // ตั้งค่าวันที่เป็นวันนี้
            const today = new Date();
            startDateInput.value = today.toISOString().split('T')[0];
        }
        
        if (startTimeInput && !startTimeInput.value) {
            // ตั้งค่าเวลาเป็นชั่วโมงถัดไป
            const now = new Date();
            now.setHours(now.getHours() + 1, 0, 0, 0); // ปัดเป็นชั่วโมงถัดไป
            startTimeInput.value = now.toTimeString().substr(0, 5);
        }
    }

    cleanupCaches() {
        const now = Date.now();
        const fiveMinutesAgo = now - (5 * 60 * 1000);

        for (const [fingerprint, timestamp] of this.state.requestFingerprints.entries()) {
            if (timestamp < fiveMinutesAgo) {
                this.state.requestFingerprints.delete(fingerprint);
            }
        }

        for (const [fingerprint, timestamp] of this.state.lastRequestTimes.entries()) {
            if (timestamp < fiveMinutesAgo) {
                this.state.lastRequestTimes.delete(fingerprint);
            }
        }
    }

    // === Core Methods ===
    setupSweetAlert2() {
        if (typeof Swal !== 'undefined') {
            this.state.toastMixin = Swal.mixin({
                toast: true,
                position: 'top-end',
                showConfirmButton: false,
                timer: 3000,
                timerProgressBar: true,
                didOpen: (toast) => {
                    toast.addEventListener('mouseenter', Swal.stopTimer);
                    toast.addEventListener('mouseleave', Swal.resumeTimer);
                }
            });
        } else {
            this.log('warn', 'SweetAlert2 not found. Using fallback notifications.');
            this.state.toastMixin = { 
                fire: (options) => this.showFallbackNotification(options.title, options.icon, { duration: options.timer }) 
            };
        }
    }
    
    log(level, message, ...args) {
        if (!this.config.debug && level === 'debug') return;
        const timestamp = new Date().toISOString();
        const logMessage = `[${timestamp}] [${level.toUpperCase()}] ${message}`;
        switch (level) {
            case 'error': console.error(logMessage, ...args); break;
            case 'warn': console.warn(logMessage, ...args); break;
            case 'info': console.info(logMessage, ...args); break;
            default: console.log(logMessage, ...args);
        }
    }
    
    async httpRequest(url, options = {}) {
        const defaultHeaders = {
            'X-CSRFToken': this.config.csrfToken,
            'X-Requested-With': 'XMLHttpRequest'
        };
        
        // **ไม่ตั้ง Content-Type: application/json เป็น default เพราะอาจขัดแย้งกับ FormData**
        if (options.body && typeof options.body === 'string') {
            // ถ้า body เป็น string (JSON) ให้ตั้ง Content-Type เป็น application/json
            defaultHeaders['Content-Type'] = 'application/json';
        }
        // ถ้า body เป็น FormData ไม่ต้องตั้ง Content-Type ให้ browser จัดการ
        
        const defaultOptions = {
            headers: { ...defaultHeaders, ...options.headers },
            credentials: 'same-origin'
        };
        const finalOptions = { ...defaultOptions, ...options };
        
        for (let attempt = 1; attempt <= this.config.retryAttempts; attempt++) {
            try {
                this.log('debug', `HTTP Request attempt ${attempt}:`, url, finalOptions);
                const response = await fetch(url, finalOptions);
                
                if (!response.ok) {
                    if (response.status === 401) {
                        this.handleUnauthorized();
                        throw new Error('Unauthorized access'); 
                    }
                    if (response.status >= 500 && attempt < this.config.retryAttempts) {
                        await this.delay(this.config.retryDelay * attempt);
                        continue;
                    }
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
                }
                
                const contentType = response.headers.get('content-type');
                if (contentType && contentType.includes('application/json')) {
                    return await response.json();
                }
                return await response.text();
            } catch (error) {
                this.log('warn', `Request attempt ${attempt} failed:`, error);
                if (attempt === this.config.retryAttempts) throw error;
                await this.delay(this.config.retryDelay * attempt);
            }
        }
    }
    
    delay(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
    
    getCSRFToken() {
        const tokenMeta = document.querySelector('meta[name="csrf-token"]');
        return tokenMeta ? tokenMeta.getAttribute('content') : '';
    }
    
    generateFormToken() {
        return crypto.randomUUID ? crypto.randomUUID() : this.generateUUID();
    }

    generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }
    
    loadUserContext() {
        try {
            const userMeta = document.querySelector('meta[name="current-user"]');
            const orgMeta = document.querySelector('meta[name="current-organization"]');
            const debugMeta = document.querySelector('meta[name="debug-mode"]');
            if (userMeta) this.state.currentUser = JSON.parse(userMeta.content);
            if (orgMeta) this.state.currentOrganization = JSON.parse(orgMeta.content);
            if (debugMeta) this.config.debug = debugMeta.content === 'True';
            this.log('debug', 'User context loaded:', this.state);
        } catch (error) {
            this.log('warn', 'Failed to load user context:', error);
        }
    }
    
    setupEventListeners() {
        window.addEventListener('error', (event) => this.reportError(event.error));
        window.addEventListener('unhandledrejection', (event) => this.reportError(event.reason));
        window.addEventListener('online', () => this.showNotification('เชื่อมต่ออินเทอร์เน็ตแล้ว', 'success'));
        window.addEventListener('offline', () => this.showNotification('ขาดการเชื่อมต่ออินเทอร์เน็ต', 'warning'));
        document.addEventListener('visibilitychange', () => document.hidden ? this.pauseOperations() : this.resumeOperations());
        document.addEventListener('keydown', (event) => this.handleKeyboardShortcuts(event));
    }
    
    initializeComponents() {
        this.initializeTooltips();
        this.initializeModals();
        this.initializeForms();
        this.initializeSubscriptionMonitoring();
        this.initializeUsageLimits();
        this.initializeDoubleClickPrevention();
        this.setupDateTimeAutoCorrection();
    }
    
    initializeTooltips() {
        if (typeof bootstrap !== 'undefined') {
            const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            tooltipTriggerList.map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));
        }
    }
    
    initializeModals() {
        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('shown.bs.modal', function () {
                const firstInput = modal.querySelector('input, select, textarea');
                if (firstInput) firstInput.focus();
            });
        });
    }
    
    initializeForms() {
        document.querySelectorAll('form').forEach(form => {
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn) submitBtn.dataset.originalHtml = submitBtn.innerHTML;

            if (!form.dataset.initializedAsync) {
                form.addEventListener('submit', (event) => {
                    // **แก้ไข: เพิ่มการตรวจสอบหน้า update_status**
                    const isUpdateStatusPage = window.location.pathname.includes('/update_status');
                    const hasAsyncFalse = form.dataset.async === 'false';
                    
                    // หากเป็นหน้า update_status หรือมี data-async="false" ให้ใช้ normal form submission
                    if (isUpdateStatusPage || hasAsyncFalse) {
                        this.log('debug', 'Using normal form submission for:', form.action || window.location.pathname);
                        return; // ให้ browser จัดการตามปกติ
                    }
                    
                    // สำหรับหน้าอื่นๆ ใช้ async
                    if (event.submitter) {
                        this.handleAsyncForm(event);
                    }
                });
                form.dataset.initializedAsync = 'true';
            }
        });
    }

    // **เพิ่ม method ใหม่สำหรับจัดการ appointment form โดยเฉพาะ**
    async createAppointment(formData) {
        try {
            this.log('info', 'Creating appointment with data:', formData);
            
            // **เพิ่ม: Validate date/time ก่อนส่งข้อมูล**
            const validation = this.validateAppointmentDateTime(formData);
            if (!validation.valid) {
                const errorMessage = validation.errors.join('\n');
                this.showNotification(errorMessage, 'error');
                return false;
            }
            
            // ตรวจสอบว่ามี form_token หรือไม่ ถ้าไม่มีให้สร้างใหม่
            if (!formData.form_token) {
                formData.form_token = this.generateFormToken();
            }
            
            // **เพิ่ม: ป้องกัน double submit**
            const fingerprint = this.generateRequestFingerprint(formData);
            if (this.state.requestFingerprints.has(fingerprint)) {
                this.showNotification('คำขอนี้ถูกส่งไปแล้ว กรุณารอสักครู่', 'warning');
                return false;
            }
            this.state.requestFingerprints.set(fingerprint, Date.now());
            
            const response = await this.httpRequest('/create_appointment', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'X-CSRFToken': this.config.csrfToken
                },
                body: JSON.stringify(formData)
            });
            
            if (response.success) {
                this.showNotification('นัดหมายถูกสร้างเรียบร้อยแล้ว', 'success');
                
                // รีเซ็ตฟอร์ม
                const form = document.getElementById('appointmentForm');
                if (form) {
                    form.reset();
                    this.clearFormErrors(form);
                }
                
                // รีเฟรช calendar หรือ events list ถ้ามี
                if (typeof this.refreshEvents === 'function') {
                    this.refreshEvents();
                }
                if (typeof this.refreshCalendar === 'function') {
                    this.refreshCalendar();
                }
                
                // ปิด modal ถ้ามี
                const modal = document.querySelector('#appointmentModal');
                if (modal && typeof bootstrap !== 'undefined') {
                    const modalInstance = bootstrap.Modal.getInstance(modal);
                    if (modalInstance) {
                        modalInstance.hide();
                    }
                }
                
                return response;
            } else {
                // จัดการ field errors
                if (response.field_errors) {
                    const form = document.getElementById('appointmentForm');
                    if (form) {
                        Object.keys(response.field_errors).forEach(fieldName => {
                            const field = form.querySelector(`[name="${fieldName}"]`);
                            if (field) {
                                this.showFieldError(field, response.field_errors[fieldName]);
                            }
                        });
                    }
                }
                
                throw new Error(response.error || 'Failed to create appointment');
            }
        } catch (error) {
            this.log('error', 'Error creating appointment:', error);
            this.showNotification(error.message || 'เกิดข้อผิดพลาดในการสร้างนัดหมาย', 'error');
            throw error;
        } finally {
            // ลบ fingerprint หลังจาก 5 วินาที
            const fingerprint = this.generateRequestFingerprint(formData);
            setTimeout(() => {
                this.state.requestFingerprints.delete(fingerprint);
            }, 5000);
        }
    }

    validateAppointmentDateTime(formData) {
        const errors = [];
        
        // ตรวจสอบว่ามีข้อมูลครับถ้วน
        if (!formData.start_date || !formData.start_time || !formData.end_date || !formData.end_time) {
            errors.push('กรุณากรอกวันที่และเวลาให้ครบถ้วน');
            return { valid: false, errors: errors };
        }
        
        try {
            // แปลง string เป็น Date objects
            const startDate = new Date(formData.start_date + 'T' + formData.start_time);
            const endDate = new Date(formData.end_date + 'T' + formData.end_time);
            const now = new Date();
            
            // ตรวจสอบว่าไม่เป็นเวลาในอดีต
            if (startDate < now) {
                errors.push('ไม่สามารถสร้างนัดหมายในเวลาที่ผ่านไปแล้ว');
            }
            
            // ตรวจสอบว่า end time หลัง start time
            if (endDate <= startDate) {
                // แก้ไขอัตโนมัติโดยเพิ่ม 1 ชั่วโมง
                const correctedEndDate = new Date(startDate.getTime() + (60 * 60 * 1000)); // เพิ่ม 1 ชั่วโมง
                
                formData.end_date = correctedEndDate.toISOString().split('T')[0];
                formData.end_time = correctedEndDate.toTimeString().substr(0, 5);
                
                this.showNotification('ปรับเวลาสิ้นสุดเป็น ' + formData.end_time + ' อัตโนมัติ', 'info');
            }
            
            // ตรวจสอบว่านัดหมายไม่เกิน 24 ชั่วโมง
            const durationMs = endDate - startDate;
            const durationHours = durationMs / (1000 * 60 * 60);
            if (durationHours > 24) {
                errors.push('ระยะเวลานัดหมายไม่ควรเกิน 24 ชั่วโมง');
            }
            
        } catch (error) {
            errors.push('รูปแบบวันที่หรือเวลาไม่ถูกต้อง');
        }
        
        return { valid: errors.length === 0, errors: errors };
    }

    
    async handleAsyncForm(event) {
        event.preventDefault();
        
        const form = event.target;
        const formId = form.id || `form_${Date.now()}`;
        const submitButton = form.querySelector('button[type="submit"]');
        
        if (this.state.submittingForms.has(formId)) {
            this.log('warn', 'Form submission already in progress:', formId);
            this.showNotification('กำลังประมวลผลอยู่ กรุณารอสักครู่', 'info');
            return false;
        }

        if (submitButton) this.setLoadingState(submitButton, true);
        this.state.submittingForms.add(formId);

        const formData = new FormData(form);
        const data = Object.fromEntries(formData.entries());

        // **แก้ไขสำคัญ: จัดการ checkbox และ boolean values**
        Object.keys(data).forEach(key => {
            const element = form.querySelector(`[name="${key}"]`);
            if (element && element.type === 'checkbox') {
                data[key] = element.checked;
            }
            // แปลงค่า "true"/"false" string เป็น boolean
            if (data[key] === 'true') data[key] = true;
            if (data[key] === 'false') data[key] = false;
        });

        try {
            const fingerprint = this.generateRequestFingerprint(data);
            if (this.state.requestFingerprints.has(fingerprint)) {
                throw new Error('คำขอเดียวกันถูกส่งไปแล้ว กรุณารอสักครู่');
            }
            if (!this.checkRapidRequest(fingerprint)) {
                throw new Error('กรุณารอสักครู่ก่อนส่งคำขอใหม่');
            }
            this.state.requestFingerprints.set(fingerprint, Date.now());
            
            this.clearFormErrors(form);
            
            const requestId = `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
            
            // **แก้ไขหลัก: ตรวจสอบ endpoint และจัดการ headers ให้ถูกต้อง**
            const isAppointmentForm = form.action.includes('/create_appointment') || form.id === 'appointmentForm';
            
            let requestOptions;
            if (isAppointmentForm) {
                // สำหรับ appointment form ส่งเป็น JSON
                requestOptions = {
                    method: form.method || 'POST',
                    headers: { 
                        'Content-Type': 'application/json',  // **สำคัญ: ต้องมี header นี้**
                        'Accept': 'application/json',
                        'X-Request-ID': requestId, 
                        'X-Idempotency-Key': fingerprint,
                        'X-CSRFToken': this.config.csrfToken
                    },
                    body: JSON.stringify({ ...data, request_id: requestId })
                };
            } else {
                // สำหรับ form อื่นๆ ส่งเป็น FormData
                const formDataToSend = new FormData();
                Object.keys(data).forEach(key => {
                    formDataToSend.append(key, data[key]);
                });
                formDataToSend.append('request_id', requestId);
                
                requestOptions = {
                    method: form.method || 'POST',
                    headers: { 
                        'Accept': 'application/json',
                        'X-Request-ID': requestId, 
                        'X-Idempotency-Key': fingerprint,
                        'X-CSRFToken': this.config.csrfToken
                        // **ไม่ตั้ง Content-Type สำหรับ FormData ให้ browser จัดการเอง**
                    },
                    body: formDataToSend
                };
            }
            
            const response = await this.httpRequest(form.action, requestOptions);
            
            if (response.success) {
                this.showNotification(response.message || 'บันทึกข้อมูลสำเร็จ', 'success');
                this.handleFormSuccess(form, response);
                return true;
            } else {
                if (response.field_errors) {
                    Object.keys(response.field_errors).forEach(fieldName => {
                        this.showFieldError(form.querySelector(`[name="${fieldName}"]`), response.field_errors[fieldName]);
                    });
                }
                throw new Error(response.error || 'Form submission failed');
            }
        } catch (error) {
            this.log('error', 'Form submission error:', error);
            if (!error.field_errors) {
                this.showNotification(error.message || 'เกิดข้อผิดพลาดในการส่งข้อมูล', 'error');
            }
            return false;
        } finally {
            this.state.submittingForms.delete(formId);
            if (submitButton) this.setLoadingState(submitButton, false);
            
            const fingerprint = this.generateRequestFingerprint(data);
            setTimeout(() => {
                this.state.requestFingerprints.delete(fingerprint);
            }, 5000);
        }
    }
    
    setLoadingState(element, loading = true) {
        if (!element) return;
        if (loading) {
            if (!element.dataset.originalDisabled) element.dataset.originalDisabled = element.disabled.toString();
            if (!element.dataset.originalHtml) element.dataset.originalHtml = element.innerHTML;
            element.disabled = true;
            element.style.pointerEvents = 'none';
            element.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>กำลังประมวลผล...';
            element.classList.add('loading');
        } else {
            element.disabled = element.dataset.originalDisabled === 'true';
            element.style.pointerEvents = '';
            element.innerHTML = element.dataset.originalHtml || element.innerHTML;
            element.classList.remove('loading');
            delete element.dataset.originalDisabled;
            delete element.dataset.originalHtml;
        }
    }

    // === Form Error Handling ===
    showFieldError(field, message) {
        if (!field) return;
        field.classList.remove('is-valid');
        field.classList.add('is-invalid');
        
        let errorDiv = field.parentNode.querySelector('.invalid-feedback');
        if (!errorDiv) {
            errorDiv = document.createElement('div');
            errorDiv.className = 'invalid-feedback';
            field.parentNode.appendChild(errorDiv);
        }
        errorDiv.textContent = message;
    }

    clearFieldError(field) {
        if (!field) return;
        field.classList.remove('is-invalid');
        field.classList.add('is-valid');
        
        const errorDiv = field.parentNode.querySelector('.invalid-feedback');
        if (errorDiv) {
            errorDiv.textContent = '';
        }
    }

    clearFormErrors(form) {
        form.querySelectorAll('.is-invalid').forEach(field => {
            this.clearFieldError(field);
        });
        
        form.querySelectorAll('.field-error').forEach(div => {
            div.textContent = '';
        });
    }

    handleFormSuccess(form, response) {
        form.reset();
        if (response.redirect_url) {
            setTimeout(() => { window.location.href = response.redirect_url; }, 1000);
        }
    }

    // === Error Handling & Reporting ===
    setupErrorHandling() {
        this.errorQueue = [];
        this.maxErrorQueueSize = 10;
    }

    reportError(error, context = {}) {
        const errorReport = {
            message: error.message || String(error),
            stack: error.stack,
            timestamp: new Date().toISOString(),
            url: window.location.href,
            userAgent: navigator.userAgent,
            userId: this.state.currentUser?.id,
            organizationId: this.state.currentOrganization?.id,
            context: context
        };
        
        this.log('error', 'Error reported:', errorReport);
        this.sendErrorReport(errorReport).catch(err => {
            this.log('warn', 'Failed to send error report:', err);
        });
    }

    async sendErrorReport(errorReport) {
        try {
            await this.httpRequest('/api/errors', {
                method: 'POST',
                body: JSON.stringify(errorReport)
            });
        } catch (error) {
            this.log('warn', 'Failed to send error report:', error);
        }
    }

    handleUnauthorized() {
        this.showNotification('กรุณาเข้าสู่ระบบใหม่', 'warning');
        setTimeout(() => {
            window.location.href = '/auth/login';
        }, 2000);
    }

    // === Keyboard Shortcuts ===
    handleKeyboardShortcuts(event) {
        if ((event.ctrlKey || event.metaKey) && event.key === 'k') {
            event.preventDefault();
            const searchInput = document.querySelector('#quickSearch');
            if (searchInput) {
                searchInput.focus();
            }
        }
        
        if ((event.ctrlKey || event.metaKey) && event.key === 'n') {
            event.preventDefault();
            const newButton = document.querySelector('#new-appointment, .btn-new');
            if (newButton && !newButton.disabled) {
                newButton.click();
            }
        }
        
        if (event.key === 'Escape') {
            const openModal = document.querySelector('.modal.show');
            if (openModal && typeof bootstrap !== 'undefined') {
                const modal = bootstrap.Modal.getInstance(openModal);
                if (modal) {
                    modal.hide();
                }
            }
        }
    }

    // === Lifecycle Management ===
    pauseOperations() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
        }
        this.log('debug', 'Operations paused');
    }

    resumeOperations() {
        this.startHeartbeat();
        this.log('debug', 'Operations resumed');
    }

    // === Subscription Monitoring ===
    initializeSubscriptionMonitoring() {
        if (!this.state.currentOrganization) {
            this.log('debug', 'No currentOrganization data for subscription monitoring.');
            return;
        }
        
        this.checkTrialStatus();
        this.checkSubscriptionStatus();
        
        setInterval(() => {
            this.checkTrialStatus();
            this.checkSubscriptionStatus();
        }, 300000);
    }

    checkTrialStatus() {
        if (!this.state.currentOrganization) return;
        
        const trialEnds = this.state.currentOrganization.trial_ends_at;
        const subscriptionStatus = this.state.currentOrganization.subscription_status;
        
        if (subscriptionStatus === 'trial' && trialEnds) {
            const trialEndDate = new Date(trialEnds);
            const now = new Date();
            const daysLeft = Math.ceil((trialEndDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
            
            if (daysLeft <= 3 && daysLeft > 0) {
                this.showTrialWarning(daysLeft);
            } else if (daysLeft <= 0) {
                this.showTrialExpired();
            }
        }
    }

    showTrialWarning(daysLeft) {
        const lastShown = localStorage.getItem('trial_warning_shown');
        const now = Date.now();
        
        if (lastShown && (now - parseInt(lastShown)) < (1 * 60 * 60 * 1000)) {
            return;
        }
        
        this.showNotification(
            `การทดลองใช้จะหมดอายุในอีก ${daysLeft} วัน กรุณาเลือกแพ็คเกจเพื่อใช้งานต่อ`,
            'warning'
        );
        
        localStorage.setItem('trial_warning_shown', now.toString());
    }

    showTrialExpired() {
        this.showNotification(
            'การทดลองใช้หมดอายุแล้ว ฟีเจอร์บางอย่างอาจถูกจำกัด',
            'error'
        );
    }

    checkSubscriptionStatus() {
        if (!this.state.currentOrganization) return;
        
        const status = this.state.currentOrganization.subscription_status;
        
        if (status === 'suspended') {
            this.handleSuspendedAccount();
        } else if (status === 'cancelled') {
            this.handleCancelledAccount();
        }
    }

    handleSuspendedAccount() {
        this.showNotification('บัญชีของคุณถูกระงับการใช้งาน กรุณาอัพเกรดแพ็คเกจ', 'error');
    }

    handleCancelledAccount() {
        this.showNotification(
            'การสมัครสมาชิกถูกยกเลิกแล้ว คุณจะใช้งานได้ถึงวันหมดอายุ',
            'info'
        );
    }

    // === Usage Limits Monitoring ===
    initializeUsageLimits() {
        this.checkUsageLimits();
        
        setInterval(() => {
            this.checkUsageLimits();
        }, 120000);
    }

    async checkUsageLimits() {
        try {
            const response = await this.httpRequest('/api/usage-stats');
            
            if (response.success && response.data) {
                this.updateUsageIndicators(response.data);
                
                if (!response.data.can_create_appointment) {
                    this.showNotification(
                        `คุณใช้งานนัดหมายครบ ${response.data.monthly_appointments} รายการแล้ว กรุณาอัปเกรดแพ็คเกจ`,
                        'warning'
                    );
                }
                
                if (!response.data.can_add_staff) {
                    this.showNotification(
                        'คุณใช้งานเจ้าหน้าที่ครบขีดจำกัดแล้ว กรุณาอัปเกรดแพ็คเกจ',
                        'warning'
                    );
                }
            }
        } catch (error) {
            this.log('warn', 'Failed to check usage limits:', error);
        }
    }

    updateUsageIndicators(data) {
        const apptUsageText = document.querySelector('.usage-appointments-text');
        if (apptUsageText) {
            apptUsageText.textContent = `${data.monthly_appointments} / ${data.max_appointments === -1 ? '∞' : data.max_appointments}`;
        }
        
        const staffUsageText = document.querySelector('.usage-staff-text');
        if (staffUsageText) {
            staffUsageText.textContent = `${data.monthly_staff || 0} / ${data.max_staff === -1 ? '∞' : data.max_staff}`;
        }
        
        this.updateProgressBar('.usage-appointments-progress .progress-bar', data.appointment_usage_percent);
        this.updateProgressBar('.usage-staff-progress .progress-bar', data.staff_usage_percent);
    }

    updateProgressBar(selector, percentage) {
        const progressBar = document.querySelector(selector);
        if (progressBar && percentage !== undefined) {
            progressBar.style.width = `${Math.min(percentage, 100)}%`;
            progressBar.className = `progress-bar ${this.getProgressBarClass(percentage)}`;
        }
    }

    getProgressBarClass(percentage) {
        if (percentage >= 90) return 'bg-danger';
        if (percentage >= 80) return 'bg-warning';
        return 'bg-success';
    }

    // === Notification System ===
    showNotification(message, type = 'info', options = {}) {
        if (this.state.toastMixin) {
            this.state.toastMixin.fire({
                icon: type === 'error' ? 'error' : type === 'success' ? 'success' : 'info',
                title: message
            });
        } else {
            this.showFallbackNotification(message, type, options);
        }
    }

    showFallbackNotification(message, type, options = {}) {
        const defaults = { duration: 5000, position: 'top-right', closable: true };
        const settings = { ...defaults, ...options };

        const notification = document.createElement('div');
        notification.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
        notification.style.cssText = `
            top: 20px; right: 20px; z-index: 9999; 
            min-width: 300px; max-width: 500px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        `;
        
        notification.innerHTML = `
            ${this.escapeHtml(message)}
            ${settings.closable ? '<button type="button" class="btn-close" data-bs-dismiss="alert"></button>' : ''}
        `;
        
        document.body.appendChild(notification);
        
        if (settings.duration > 0) {
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.remove();
                }
            }, settings.duration);
        }
    }

    // === Utility Methods ===
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // === Heartbeat & Connection ===
    startHeartbeat() {
        this.heartbeatInterval = setInterval(() => {
            this.sendHeartbeat();
            this.cleanupCaches();
        }, 60000);
    }
    
    async sendHeartbeat() {
        try {
            await this.httpRequest('/api/heartbeat', { method: 'POST' });
            this.log('debug', 'Heartbeat sent.');
        } catch (error) {
            this.log('warn', 'Heartbeat failed:', error);
        }
    }
    
    // === Event and Appointment Management Methods ===

    /**
     * โหลดรายการนัดหมาย (สำหรับหน้ารายการนัดหมาย)
     */
    async loadAppointments() {
        const container = document.getElementById('appointments-container');
        if (!container) {
            this.log('debug', 'appointments-container not found');
            return;
        }
        
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
        
        try {
            // สร้าง URL พร้อมพารามิเตอร์
            let url = '/get_events';
            const params = new URLSearchParams();
            
            if (subcalendarId) params.append('subcalendar_id', subcalendarId);
            if (startDate) params.append('start_date', startDate);
            if (endDate) params.append('end_date', endDate);
            
            if (params.toString()) {
                url += '?' + params.toString();
            }
            
            this.log('debug', 'Loading appointments from:', url);
            
            const data = await this.httpRequest(url);
            
            container.innerHTML = '';
            
            if (!data.events || data.events.length === 0) {
                container.innerHTML = `
                    <div class="alert alert-info">
                        <i class="fas fa-info-circle me-2"></i>ไม่พบรายการนัดหมายในช่วงเวลาที่เลือก
                    </div>
                `;
                return;
            }
            
            // เก็บข้อมูล events ไว้ใน state สำหรับใช้งานภายหลัง
            this.state.currentEvents = data.events;
            
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
                const formattedDate = this.formatDate(date);
                
                container.innerHTML += `
                    <h4 class="mt-4 mb-3">
                        <i class="far fa-calendar-alt me-2"></i>${formattedDate}
                    </h4>
                    <div class="mb-2">
                        <span class="badge bg-primary">${eventsByDate[date].length} รายการ</span>
                    </div>
                `;
                
                eventsByDate[date].forEach(event => {
                    container.appendChild(this.createEventCard(event));
                });
            });
            
            // ผูกเหตุการณ์ใหม่สำหรับปุ่มดูรายละเอียดที่เพิ่งสร้าง
            this.setupEventHandlers();
            
            this.log('info', `Loaded ${data.events.length} appointments`);
            
        } catch (error) {
            this.log('error', 'Error loading appointments:', error);
            container.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>เกิดข้อผิดพลาดในการโหลดรายการนัดหมาย: ${error.message}
                </div>
            `;
        }
    }

    /**
     * แสดงรายละเอียดนัดหมายใน modal
     */
    async showEventDetails(eventId) {
        this.log('debug', "แสดงรายละเอียดสำหรับ event_id:", eventId);
        
        try {
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
            const data = await this.httpRequest(`/get_events?event_id=${eventId}`);
            
            // **เพิ่ม debug log เพื่อดูข้อมูลที่ได้**
            console.log('Event data received:', data);
            if (data.events && data.events.length > 0) {
                console.log('Event object:', data.events[0]);
                console.log('Available subcalendar fields:', Object.keys(data.events[0]).filter(key => key.includes('subcal') || key.includes('calendar')));
            }
            
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
                    this.showNotification('ไม่พบข้อมูลนัดหมายสำหรับ ID นี้', 'warning');
                }
                return;
            }
            
            // ดึงข้อมูลนัดหมายจาก API response
            const event = data.events[0]; // ควรมีเพียงกิจกรรมเดียว
            
            // **ปรับปรุงการหาชื่อปฏิทิน - ลองหลายๆ field**
            let subcalendarDisplay = 'ไม่ระบุปฏิทิน';
            
            // ลองหา field ต่างๆ ที่อาจมีชื่อปฏิทิน
            if (event.subcalendar_display) {
                subcalendarDisplay = event.subcalendar_display;
            } else if (event.subcalendar_name) {
                subcalendarDisplay = event.subcalendar_name;
            } else if (event.calendar_name) {
                subcalendarDisplay = event.calendar_name;
            } else if (event.subcalendar_id) {
                // ถ้ามีแค่ ID ให้ใช้ ID แทน
                subcalendarDisplay = `Calendar ${event.subcalendar_id}`;
            } else if (event.subcalendar_ids && event.subcalendar_ids.length > 0) {
                // ถ้ามี subcalendar_ids array
                subcalendarDisplay = `Calendar ${event.subcalendar_ids[0]}`;
            }
            
            console.log('Final subcalendar display name:', subcalendarDisplay);
            
            // **ปรับปรุงการแสดงผล notes - แปลง HTML เป็นข้อความธรรมดา**
            let notesDisplay = '';
            if (event.notes) {
                // สร้าง temporary div element เพื่อแปลง HTML เป็นข้อความ
                const tempDiv = document.createElement('div');
                tempDiv.innerHTML = event.notes;
                notesDisplay = tempDiv.textContent || tempDiv.innerText || '';
                
                // ถ้าข้อความว่างเปล่า ให้ใช้ HTML เดิม
                if (!notesDisplay.trim()) {
                    notesDisplay = event.notes;
                }
            }
            
            // สร้าง modal แสดงรายละเอียด
            if (typeof Swal !== 'undefined') {
                Swal.fire({
                    title: 'รายละเอียดนัดหมาย',
                    html: `
                        <div class="text-start">
                            <h5>${this.escapeHtml(event.title)}</h5>
                            <div class="mb-3">
                                <span class="badge bg-secondary">
                                    <i class="fas fa-calendar me-1"></i>${this.escapeHtml(subcalendarDisplay)}
                                </span>
                            </div>
                            <p><strong>วันที่:</strong> ${this.formatDate(event.start_dt.split('T')[0])}</p>
                            <p><strong>เวลา:</strong> ${event.start_dt.split('T')[1].substring(0, 5)} - ${event.end_dt.split('T')[1].substring(0, 5)}</p>
                            <p><strong>สถานที่:</strong> ${this.escapeHtml(event.location || 'ไม่ระบุ')}</p>
                            <p><strong>ผู้ดูแล:</strong> ${this.escapeHtml(event.who || 'ไม่ระบุ')}</p>
                            ${notesDisplay ? `
                            <div class="mt-3">
                                <h6>บันทึกเพิ่มเติม:</h6>
                                <div class="border p-2 rounded bg-light">
                                    <span style="white-space: pre-wrap;">${this.escapeHtml(notesDisplay)}</span>
                                </div>
                            </div>
                            ` : ''}
                            <div class="mt-3">
                                <h6>Event ID:</h6>
                                <div class="input-group">
                                    <input type="text" class="form-control" value="${this.escapeHtml(event.id)}" readonly>
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
                    วันที่: ${this.formatDate(event.start_dt.split('T')[0])}
                    เวลา: ${event.start_dt.split('T')[1].substring(0, 5)} - ${event.end_dt.split('T')[1].substring(0, 5)}
                    สถานที่: ${event.location || 'ไม่ระบุ'}
                    ผู้ดูแล: ${event.who || 'ไม่ระบุ'}
                    Event ID: ${event.id}
                    ${notesDisplay ? `\nบันทึก: ${notesDisplay}` : ''}
                `;
                
                if (confirm(details + '\n\nต้องการอัปเดตสถานะหรือไม่?')) {
                    window.location.href = `/update_status?event_id=${event.id}`;
                }
            }
            
        } catch (error) {
            this.log('error', 'Error fetching event details:', error);
            if (typeof Swal !== 'undefined') {
                Swal.fire({
                    icon: 'error',
                    title: 'เกิดข้อผิดพลาด',
                    text: 'ไม่สามารถโหลดข้อมูลนัดหมายได้: ' + error.message
                });
            } else {
                this.showNotification('ไม่สามารถโหลดข้อมูลนัดหมายได้: ' + error.message, 'error');
            }
        }
    }

    /**
     * สร้าง event card element
     */
    createEventCard(event) {
        const card = document.createElement('div');
        
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
        
        // **ปรับปรุงการหาชื่อปฏิทิน - เหมือนกับ showEventDetails**
        let subcalendarDisplay = 'ไม่ระบุปฏิทิน';
        
        if (event.subcalendar_display) {
            subcalendarDisplay = event.subcalendar_display;
        } else if (event.subcalendar_name) {
            subcalendarDisplay = event.subcalendar_name;
        } else if (event.calendar_name) {
            subcalendarDisplay = event.calendar_name;
        } else if (event.subcalendar_id) {
            subcalendarDisplay = `Calendar ${event.subcalendar_id}`;
        } else if (event.subcalendar_ids && event.subcalendar_ids.length > 0) {
            subcalendarDisplay = `Calendar ${event.subcalendar_ids[0]}`;
        }
        
        card.className = `card appointment-card ${statusClass}`;
        card.dataset.eventId = event.id;
        card.innerHTML = `
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <div class="flex-grow-1">
                        <h5 class="card-title mb-1">${this.escapeHtml(event.title)}</h5>
                        <div class="mb-2">
                            <span class="badge bg-secondary me-2">
                                <i class="fas fa-calendar me-1"></i>${this.escapeHtml(subcalendarDisplay)}
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
                            <small>${this.escapeHtml(event.location || 'ไม่ระบุตำแหน่ง')}</small>
                        </p>
                    </div>
                    <div class="col-md-6">
                        <p class="card-text mb-1">
                            <i class="fas fa-user-md me-2 text-muted"></i>
                            <small>${this.escapeHtml(event.who || 'ไม่ระบุผู้ดูแล')}</small>
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
        `;
        
        return card;
    }

    /**
     * ตั้งค่า event handlers สำหรับปุ่มต่างๆ ในหน้ารายการนัดหมาย
     */
    setupEventHandlers() {
        // จัดการการคลิกที่ปุ่มดูรายละเอียด
        document.querySelectorAll('.view-details').forEach(button => {
            // ลบ event listener เก่าก่อน (ถ้ามี)
            button.removeEventListener('click', this.handleViewDetailsClick);
            
            // เพิ่ม event listener ใหม่
            button.addEventListener('click', this.handleViewDetailsClick.bind(this));
        });
        
        // จัดการการคลิกที่ปุ่มอัปเดตสถานะ
        document.querySelectorAll('.update-status').forEach(button => {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                const eventId = this.getAttribute('data-event-id');
                window.location.href = `/update_status?event_id=${eventId}`;
            });
        });
    }

    /**
     * Handler สำหรับปุ่มดูรายละเอียด
     */
    handleViewDetailsClick(event) {
        event.preventDefault();
        const eventId = event.currentTarget.getAttribute('data-event-id');
        if (eventId) {
            this.showEventDetails(eventId);
        }
    }

    /**
     * แปลงรูปแบบวันที่เป็นภาษาไทย
     */
    formatDate(dateString) {
        try {
            const date = new Date(dateString);
            return date.toLocaleDateString('th-TH', {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
                weekday: 'long'
            });
        } catch (error) {
            this.log('warn', 'Error formatting date:', error);
            return dateString;
        }
    }

    /**
     * รีเฟรช events (สำหรับเรียกใช้หลังจากสร้างนัดหมายใหม่)
     */
    refreshEvents() {
        this.loadAppointments();
    }

    /**
     * รีเฟรช calendar (สำหรับ compatibility)
     */
    refreshCalendar() {
        this.loadAppointments();
    }

    // === Cleanup ===
    destroy() {
        if (this.heartbeatInterval) clearInterval(this.heartbeatInterval);
        this.eventHandlers.clear();
        this.state.eventsCache.clear();
        this.state.formTokens.clear();
        this.state.submittingForms.clear();
        this.state.lastRequestTimes.clear();
        this.state.requestFingerprints.clear();
    }
}

// === Global Initialization ===
document.addEventListener('DOMContentLoaded', function() {
    try {
        window.app = new NudDeeSaaSApp();
        
        // **เพิ่มการจัดการ appointment form โดยเฉพาะ**
        const appointmentForm = document.getElementById('appointmentForm');
        if (appointmentForm) {
            // ป้องกันไม่ให้ form ถูก handle โดย handleAsyncForm generic
            appointmentForm.dataset.async = 'false';
            
            appointmentForm.addEventListener('submit', async function(event) {
                event.preventDefault();
                
                const submitButton = appointmentForm.querySelector('button[type="submit"]');
                if (submitButton && submitButton.disabled) {
                    console.log('Submit button is disabled, ignoring submission');
                    return;
                }
                
                try {
                    if (window.app) {
                        // ใช้ loading state
                        if (submitButton) {
                            window.app.setLoadingState(submitButton, true);
                        }
                        
                        // รวบรวมข้อมูลจากฟอร์ม
                        const formData = new FormData(appointmentForm);
                        const data = {};
                        
                        // แปลง FormData เป็น object
                        for (let [key, value] of formData.entries()) {
                            const element = appointmentForm.querySelector(`[name="${key}"]`);
                            if (element && element.type === 'checkbox') {
                                data[key] = element.checked;
                            } else if (value === 'true') {
                                data[key] = true;
                            } else if (value === 'false') {
                                data[key] = false;
                            } else {
                                data[key] = value;
                            }
                        }
                        
                        // เพิ่ม form_token ถ้าไม่มี
                        if (!data.form_token) {
                            data.form_token = window.app.generateFormToken();
                        }
                        
                        console.log('Submitting appointment data:', data);
                        
                        // เรียกใช้ method createAppointment
                        await window.app.createAppointment(data);
                        
                    } else {
                        throw new Error('App instance not found');
                    }
                } catch (error) {
                    console.error('Error submitting appointment form:', error);
                    if (window.app) {
                        window.app.showNotification(
                            error.message || 'เกิดข้อผิดพลาดในการสร้างนัดหมาย', 
                            'error'
                        );
                    } else {
                        alert('เกิดข้อผิดพลาดในการสร้างนัดหมาย กรุณาลองใหม่อีกครั้ง');
                    }
                } finally {
                    // ปิด loading state
                    if (submitButton && window.app) {
                        window.app.setLoadingState(submitButton, false);
                    }
                }
            });
        }
        
        // **เพิ่มการจัดการ button click โดยตรงด้วย (เผื่อกรณีที่มี button แยก)**
        const createAppointmentBtn = document.getElementById('createAppointmentBtn');
        if (createAppointmentBtn) {
            createAppointmentBtn.addEventListener('click', function(event) {
                event.preventDefault();
                const form = document.getElementById('appointmentForm');
                if (form) {
                    // Trigger form submission event
                    const submitEvent = new Event('submit', { cancelable: true, bubbles: true });
                    form.dispatchEvent(submitEvent);
                }
            });
        }
        
    } catch (error) {
        console.error('Failed to initialize NudDee SaaS App:', error);
        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert alert-danger position-fixed';
        alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 9999;';
        alertDiv.textContent = 'เกิดข้อผิดพลาดร้ายแรงในการเริ่มต้นระบบ กรุณารีเฟรชหน้าเว็บ';
        document.body.appendChild(alertDiv);
    }

    // Inject CSS for loading state
    const loadingStyles = `
    <style id="double-submit-styles">
    .loading {
        position: relative;
        opacity: 0.7;
    }
    .loading::after {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(255, 255, 255, 0.3);
        pointer-events: none;
        border-radius: inherit;
    }
    button.loading, button:disabled {
        cursor: not-allowed !important;
        opacity: 0.6;
    }
    </style>
    `;
    if (!document.querySelector('#double-submit-styles')) {
        document.head.insertAdjacentHTML('beforeend', loadingStyles);
    }
});