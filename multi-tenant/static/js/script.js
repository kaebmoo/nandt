// static/js/script.js - Production-ready JavaScript

class NudDeeSaaSApp {
    constructor() {
        this.config = {
            debug: window.DEBUG || false, // Assuming DEBUG is set globally or from Flask config
            apiBaseUrl: window.API_BASE_URL || '', // Assuming API_BASE_URL is set globally
            csrfToken: this.getCSRFToken(),
            retryAttempts: 3,
            retryDelay: 1000
        };
        
        this.state = {
            currentUser: null,
            currentOrganization: null,
            eventsCache: new Map(),
            formTokens: new Set(),
            toastMixin: null // To store the SweetAlert2 Toast mixin
        };
        
        this.eventHandlers = new Map();
        this.init();
    }
    
    init() {
        try {
            this.setupSweetAlert2(); // Initialize SweetAlert2 mixin
            this.loadUserContext();
            this.setupEventListeners();
            this.initializeComponents();
            this.setupErrorHandling();
            this.startHeartbeat();
            
            // Set moment locale to Thai (as per your dashboard.html)
            if (typeof moment !== 'undefined') {
                moment.locale('th');
            }

            this.log('info', 'NudDee SaaS App initialized successfully');
        } catch (error) {
            this.log('error', 'Failed to initialize app:', error);
            this.showNotification('เกิดข้อผิดพลาดในการเริ่มต้นระบบ', 'error'); // Use its own notification
        }
    }

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
            this.log('warn', 'SweetAlert2 (Swal) not found. Falling back to basic notifications.');
            this.state.toastMixin = { fire: (options) => this.showFallbackNotification(options.title, options.icon, { duration: options.timer }) };
        }
    }
    
    // Logging system
    log(level, message, ...args) {
        if (!this.config.debug && level === 'debug') return;
        
        const timestamp = new Date().toISOString();
        const logMessage = `[${timestamp}] [${level.toUpperCase()}] ${message}`;
        
        switch (level) {
            case 'error':
                console.error(logMessage, ...args);
                break;
            case 'warn':
                console.warn(logMessage, ...args);
                break;
            case 'info':
                console.info(logMessage, ...args);
                break;
            default:
                console.log(logMessage, ...args);
        }
    }
    
    // HTTP client with retry logic
    async httpRequest(url, options = {}) {
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.config.csrfToken,
                ...options.headers
            },
            credentials: 'same-origin'
        };
        
        const finalOptions = { ...defaultOptions, ...options };
        
        for (let attempt = 1; attempt <= this.config.retryAttempts; attempt++) {
            try {
                this.log('debug', `HTTP Request attempt ${attempt}:`, url);
                
                const response = await fetch(url, finalOptions);
                
                if (!response.ok) {
                    if (response.status === 401) {
                        this.handleUnauthorized();
                        // Do not retry on 401 if it's already handled
                        throw new Error('Unauthorized access'); 
                    }
                    
                    if (response.status >= 500 && attempt < this.config.retryAttempts) {
                        await this.delay(this.config.retryDelay * attempt);
                        continue;
                    }
                    
                    // Try to parse JSON error, fallback to text
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
                
                if (attempt === this.config.retryAttempts) {
                    throw error; // Re-throw final error
                }
                
                await this.delay(this.config.retryDelay * attempt);
            }
        }
    }
    
    // Utility functions
    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
    
    getCSRFToken() {
        const tokenMeta = document.querySelector('meta[name="csrf-token"]');
        return tokenMeta ? tokenMeta.getAttribute('content') : '';
    }
    
    generateFormToken() {
        return crypto.randomUUID ? crypto.randomUUID() : this.generateUUID(); // Fallback for older browsers
    }
    
    generateUUID() {
        // Simple UUID v4 polyfill
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }
    
    // User context management
    loadUserContext() {
        try {
            const userMeta = document.querySelector('meta[name="current-user"]');
            const orgMeta = document.querySelector('meta[name="current-organization"]');
            const debugMeta = document.querySelector('meta[name="debug-mode"]'); // Assuming you add this in base.html
            
            if (userMeta) {
                this.state.currentUser = JSON.parse(userMeta.content);
            }
            
            if (orgMeta) {
                this.state.currentOrganization = JSON.parse(orgMeta.content);
            }

            if (debugMeta) {
                this.config.debug = debugMeta.content === 'True';
            }
            
            this.log('debug', 'User context loaded:', this.state);
        } catch (error) {
            this.log('warn', 'Failed to load user context:', error);
        }
    }
    
    // Event handling system
    setupEventListeners() {
        window.addEventListener('error', (event) => {
            this.log('error', 'Global error:', event.error);
            this.reportError(event.error);
        });
        
        window.addEventListener('unhandledrejection', (event) => {
            this.log('error', 'Unhandled promise rejection:', event.reason);
            this.reportError(event.reason);
        });
        
        window.addEventListener('online', () => {
            this.showNotification('เชื่อมต่ออินเทอร์เน็ตแล้ว', 'success');
            this.syncPendingData();
        });
        
        window.addEventListener('offline', () => {
            this.showNotification('ขาดการเชื่อมต่ออินเทอร์เน็ต', 'warning');
        });
        
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.pauseOperations();
            } else {
                this.resumeOperations();
            }
        });
        
        document.addEventListener('keydown', (event) => {
            this.handleKeyboardShortcuts(event);
        });
    }
    
    // Component initialization
    initializeComponents() {
        this.initializeTooltips();
        this.initializeModals();
        this.initializeForms();
        this.initializeSubscriptionMonitoring();
        this.initializeUsageLimits();

        // Initialize moment.js for dashboard if loaded
        if (typeof moment !== 'undefined') {
            moment.locale('th'); // Set locale globally for moment.js
        }
    }
    
    initializeTooltips() {
        if (typeof bootstrap !== 'undefined') {
            const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            tooltipTriggerList.map(function(tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        }
    }
    
    initializeModals() {
        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('shown.bs.modal', function() {
                const firstInput = modal.querySelector('input, select, textarea');
                if (firstInput) {
                    firstInput.focus();
                }
            });
        });
    }
    
    initializeForms() {
        // Use a more specific selector if forms are not all async
        document.querySelectorAll('form').forEach(form => { // Changed selector from data-async="true" to all forms
            // Store original HTML for submit buttons initially
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.dataset.originalHtml = submitBtn.innerHTML;
            }

            // Only attach handleAsyncForm if not already attached via specific template code
            // (e.g., register.html, appointments.html might attach it directly)
            // Or remove inline addEventListener in templates if using this global one
            if (!form.dataset.initializedAsync) { // Prevent duplicate listeners
                form.addEventListener('submit', (event) => {
                    // Check if the form has a submit button and prevent default only if it's an async form
                    if (event.submitter && form.dataset.async !== 'false') { // Assuming forms default to async unless data-async="false"
                        this.handleAsyncForm(event);
                    }
                });
                form.dataset.initializedAsync = 'true';
            }
        });
        
        document.querySelectorAll('form[data-autosave="true"]').forEach(form => {
            this.setupAutoSave(form);
        });
        
        document.querySelectorAll('form[data-validate="true"]').forEach(form => {
            this.setupFormValidation(form);
        });
    }
    
    async handleAsyncForm(event) {
        event.preventDefault();
        
        const form = event.target;
        const submitButton = form.querySelector('button[type="submit"]');
        const formData = new FormData(form);
        
        // Convert FormData to plain object for JSON submission
        const data = {};
        for (let [key, value] of formData.entries()) {
            data[key] = value;
        }

        try {
            const formToken = data['form_token']; // Access token from the converted object
            if (formToken && this.state.formTokens.has(formToken)) {
                this.showNotification('กำลังประมวลผลคำขออยู่', 'info');
                return false; // Prevent further processing
            }
            
            if (formToken) {
                this.state.formTokens.add(formToken);
            }
            
            this.setLoadingState(submitButton, true);
            this.clearFormErrors(form);
            
            const response = await this.httpRequest(form.action, {
                method: form.method || 'POST',
                body: JSON.stringify(data) // Send as JSON
            });
            
            if (response.success) {
                this.showNotification(response.message || 'บันทึกข้อมูลสำเร็จ', 'success');
                this.handleFormSuccess(form, response);
                return true; // Indicate success
            } else {
                // If API returns field_errors, handle them
                if (response.field_errors) {
                    Object.keys(response.field_errors).forEach(fieldName => {
                        this.showFieldError(form.querySelector(`[name="${fieldName}"]`), response.field_errors[fieldName]);
                    });
                }
                throw new Error(response.error || 'Form submission failed');
            }
            
        } catch (error) {
            this.log('error', 'Form submission error:', error);
            // Don't show notification twice if field_errors were already handled and threw
            if (!error.field_errors) {
                this.showNotification(error.message || 'เกิดข้อผิดพลาดในการส่งข้อมูล', 'error');
            }
            return false; // Indicate failure
        } finally {
            this.setLoadingState(submitButton, false);
            const formToken = data['form_token'];
            if (formToken) {
                setTimeout(() => {
                    this.state.formTokens.delete(formToken);
                }, 5000); // Allow some time before token can be reused
            }
        }
    }
    
    setupFormValidation(form) {
        const inputs = form.querySelectorAll('input, select, textarea');
        
        inputs.forEach(input => {
            input.addEventListener('blur', () => {
                this.validateField(input);
            });
            
            input.addEventListener('input', () => {
                if (input.classList.contains('is-invalid')) {
                    this.validateField(input);
                }
            });
        });
    }
    
    validateField(field) {
        const value = field.value.trim();
        const rules = this.getValidationRules(field);
        
        for (const rule of rules) {
            const isValid = rule.validate(value);
            if (!isValid) {
                this.showFieldError(field, rule.message);
                return false;
            }
        }
        
        this.clearFieldError(field);
        return true;
    }
    
    getValidationRules(field) {
        const rules = [];
        
        if (field.required) {
            rules.push({
                validate: (value) => value.length > 0,
                message: 'กรุณากรอกข้อมูลในช่องนี้'
            });
        }
        
        if (field.type === 'email') {
            rules.push({
                validate: (value) => !value || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value),
                message: 'รูปแบบอีเมลไม่ถูกต้อง'
            });
        }
        
        if (field.type === 'password') {
            // Minimal password validation here, server-side validation is more robust
            rules.push({
                validate: (value) => !value || value.length >= 8,
                message: 'รหัสผ่านต้องมีอย่างน้อย 8 ตัวอักษร'
            });
        }
        
        if (field.dataset.minLength) {
            const minLength = parseInt(field.dataset.minLength);
            rules.push({
                validate: (value) => value.length >= minLength, // Apply only if value exists
                message: `ต้องมีอย่างน้อย ${minLength} ตัวอักษร`
            });
        }
        
        if (field.dataset.maxLength) {
            const maxLength = parseInt(field.dataset.maxLength);
            rules.push({
                validate: (value) => value.length <= maxLength, // Apply only if value exists
                message: `ต้องไม่เกิน ${maxLength} ตัวอักษร`
            });
        }
        
        return rules;
    }
    
    showFieldError(field, message) {
        if (!field) return; // Guard against null field
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
        if (!field) return; // Guard against null field
        field.classList.remove('is-invalid');
        field.classList.add('is-valid');
        
        const errorDiv = field.parentNode.querySelector('.invalid-feedback');
        if (errorDiv) {
            errorDiv.textContent = '';
        }
    }
    
    clearFormErrors(form) {
        form.querySelectorAll('.is-invalid').forEach(field => {
            this.clearFieldError(field); // Use instance method
        });
        
        form.querySelectorAll('.field-error').forEach(div => { // For custom field-error divs
            div.textContent = '';
        });
    }

    // Auto-save functionality
    setupAutoSave(form) {
        const formId = form.id || `form_${Date.now()}`;
        let saveTimeout;
        
        this.loadAutoSavedData(form, formId);
        
        form.addEventListener('input', () => {
            clearTimeout(saveTimeout);
            saveTimeout = setTimeout(() => {
                this.saveFormData(form, formId);
            }, 2000);
        });
        
        form.addEventListener('submit', () => {
            this.clearAutoSavedData(formId);
        });
    }
    
    saveFormData(form, formId) {
        try {
            const formData = new FormData(form);
            const data = Object.fromEntries(formData);
            
            delete data.password;
            delete data.confirm_password;
            delete data.form_token;
            
            localStorage.setItem(`autosave_${formId}`, JSON.stringify(data));
            this.showAutoSaveNotification();
        } catch (error) {
            this.log('warn', 'Failed to auto-save form data:', error);
        }
    }
    
    loadAutoSavedData(form, formId) {
        try {
            const savedData = localStorage.getItem(`autosave_${formId}`);
            if (savedData) {
                const data = JSON.parse(savedData);
                Object.keys(data).forEach(key => {
                    const field = form.querySelector(`[name="${key}"]`);
                    if (field && field.type !== 'password') {
                        field.value = data[key];
                    }
                });
                
                this.showNotification('ข้อมูลที่บันทึกไว้ถูกกู้คืนแล้ว', 'info');
            }
        } catch (error) {
            this.log('warn', 'Failed to load auto-saved data:', error);
        }
    }
    
    clearAutoSavedData(formId) {
        localStorage.removeItem(`autosave_${formId}`);
    }
    
    showAutoSaveNotification() {
        const notification = document.createElement('div');
        notification.className = 'position-fixed bottom-0 end-0 p-3';
        notification.style.zIndex = '9999';
        notification.innerHTML = `
            <div class="toast" role="alert">
                <div class="toast-body bg-success text-white">
                    <i class="fas fa-check me-2"></i>บันทึกอัตโนมัติแล้ว
                </div>
            </div>
        `;
        
        document.body.appendChild(notification);
        
        const toast = new bootstrap.Toast(notification.querySelector('.toast'));
        toast.show();
        
        setTimeout(() => {
            notification.remove();
        }, 3000);
    }
    
    // Appointment management (Refactored to use this.httpRequest)
    async loadAppointments(filters = {}) {
        const container = document.getElementById('appointments-container');
        if (!container) {
            this.log('warn', 'Appointments container not found.');
            return;
        }
        
        const params = new URLSearchParams(filters);
        const cacheKey = params.toString();
        
        if (this.state.eventsCache.has(cacheKey)) {
            const cached = this.state.eventsCache.get(cacheKey);
            if (Date.now() - cached.timestamp < 60000) { // 1 minute cache
                this.log('debug', 'Loading appointments from cache.');
                this.displayAppointments(cached.data);
                return;
            }
        }
        
        container.innerHTML = `
            <div class="text-center p-5">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">กำลังโหลด...</span>
                </div>
                <p class="mt-2">กำลังโหลดรายการนัดหมาย...</p>
            </div>
        `;

        try {
            const response = await this.httpRequest(`/get_events?${params.toString()}`, { method: 'GET' });
            
            this.state.eventsCache.set(cacheKey, {
                data: response,
                timestamp: Date.now()
            });
            
            this.displayAppointments(response);
            
        } catch (error) {
            this.log('error', 'Failed to load appointments:', error);
            container.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>เกิดข้อผิดพลาดในการโหลดรายการนัดหมาย: ${this.escapeHtml(error.message || String(error))}
                </div>
            `;
            this.showNotification('ไม่สามารถโหลดรายการนัดหมายได้', 'error');
        }
    }
    
    displayAppointments(data) {
        const container = document.getElementById('appointments-container');
        if (!container) return;
        
        container.innerHTML = ''; // Clear loading spinner or previous content
        
        if (!data.events || data.events.length === 0) {
            container.innerHTML = `
                <div class="alert alert-info">
                    <i class="fas fa-info-circle me-2"></i>ไม่พบรายการนัดหมายในช่วงเวลาที่เลือก
                </div>
            `;
            return;
        }
        
        const eventsByDate = this.groupEventsByDate(data.events);
        
        Object.keys(eventsByDate).sort().forEach(date => {
            this.renderDateGroup(container, date, eventsByDate[date]);
        });
    }
    
    groupEventsByDate(events) {
        const groups = {};
        
        events.forEach(event => {
            const date = event.start_dt.split('T')[0];
            if (!groups[date]) {
                groups[date] = [];
            }
            groups[date].push(event);
        });
        
        return groups;
    }
    
    renderDateGroup(container, date, events) {
        const dateObj = new Date(date);
        const formattedDate = dateObj.toLocaleDateString('th-TH', {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });
        
        const dateSection = document.createElement('div');
        dateSection.innerHTML = `
            <h4 class="mt-4 mb-3">
                <i class="far fa-calendar-alt me-2"></i>${formattedDate}
            </h4>
            <div class="mb-2">
                <span class="badge bg-primary">${events.length} รายการ</span>
            </div>
        `;
        
        container.appendChild(dateSection);
        
        events.forEach(event => {
            this.renderEventCard(container, event);
        });
    }
    
    renderEventCard(container, event) {
        const startTime = event.start_dt.split('T')[1].substring(0, 5);
        const endTime = event.end_dt.split('T')[1].substring(0, 5);
        const subcalendarDisplay = event.subcalendar_display || 'ไม่ระบุปฏิทิน';
        
        let statusClass = '';
        if (event.notes && event.notes.includes('สถานะ: มาตามนัด')) { // Check notes for status
            statusClass = 'border-success';
        } else if (event.notes && event.notes.includes('สถานะ: ยกเลิก')) {
            statusClass = 'border-danger';
        } else if (event.notes && event.notes.includes('สถานะ: ไม่มา')) {
            statusClass = 'border-warning';
        } else {
            statusClass = 'border-primary'; // Default color for appointments
        }
        
        const card = document.createElement('div');
        card.className = `card appointment-card mb-3 ${statusClass}`;
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
                    <a href="/update_status?event_id=${event.id}&calendar_id=${event.source_calendar_id}" class="btn btn-sm btn-primary">
                        <i class="fas fa-edit me-1"></i>อัปเดตสถานะ
                    </a>
                    <button class="btn btn-sm btn-outline-secondary" onclick="window.app.showEventDetails('${event.id}')">
                        <i class="fas fa-info-circle me-1"></i>รายละเอียด
                    </button>
                </div>
            </div>
        `;
        
        container.appendChild(card);
    }
    
    // Event details modal
    async showEventDetails(eventId) {
        try {
            // Fetch event details including calendar_id
            const response = await this.httpRequest(`/get_events?event_id=${eventId}`);
            
            if (!response.events || response.events.length === 0) {
                this.showNotification('ไม่พบข้อมูลนัดหมาย', 'warning');
                return;
            }
            
            const event = response.events[0];
            
            // Create and show the modal
            const modalElement = document.createElement('div');
            modalElement.className = 'modal fade';
            modalElement.innerHTML = `
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">รายละเอียดนัดหมาย</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            ${this.renderEventDetails(event)}
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">ปิด</button>
                            <a href="/update_status?event_id=${event.id}&calendar_id=${event.source_calendar_id}" class="btn btn-primary">
                                <i class="fas fa-edit me-1"></i>อัปเดตสถานะ
                            </a>
                        </div>
                    </div>
                </div>
            `;
            
            document.body.appendChild(modalElement);
            const bootstrapModal = new bootstrap.Modal(modalElement);
            bootstrapModal.show();
            
            modalElement.addEventListener('hidden.bs.modal', () => {
                modalElement.remove();
            });
            
        } catch (error) {
            this.log('error', 'Failed to load event details:', error);
            this.showNotification('ไม่สามารถโหลดรายละเอียดนัดหมายได้', 'error');
        }
    }
    
    // Render event details for modal
    renderEventDetails(event) {
        const subcalendarDisplay = this.escapeHtml(event.subcalendar_display || 'ไม่ระบุปฏิทิน');
        const startDate = moment(event.start_dt).format('DD/MM/YYYY');
        const startTime = moment(event.start_dt).format('HH:mm');
        const endTime = moment(event.end_dt).format('HH:mm');
        
        return `
            <div class="row">
                <div class="col-md-8">
                    <h4>${this.escapeHtml(event.title || 'ไม่ระบุหัวข้อ')}</h4>
                    <div class="mb-3">
                        <span class="badge bg-secondary me-2">
                            <i class="fas fa-calendar me-1"></i>${subcalendarDisplay}
                        </span>
                    </div>
                </div>
                <div class="col-md-4 text-end">
                    <small class="text-muted">Event ID: ${event.id}</small><br>
                    <small class="text-muted">Calendar ID: ${event.source_calendar_id}</small>
                </div>
            </div>
            
            <div class="row mb-3">
                <div class="col-md-6">
                    <strong>วันที่:</strong> ${startDate}
                </div>
                <div class="col-md-6">
                    <strong>เวลา:</strong> ${startTime} - ${endTime}
                </div>
            </div>
            
            <div class="row mb-3">
                <div class="col-md-6">
                    <strong>สถานที่:</strong> ${this.escapeHtml(event.location || 'ไม่ระบุ')}
                </div>
                <div class="col-md-6">
                    <strong>ผู้ดูแล:</strong> ${this.escapeHtml(event.who || 'ไม่ระบุ')}
                </div>
            </div>
            
            ${event.notes ? `
                <div class="mb-3">
                    <strong>บันทึกเพิ่มเติม:</strong>
                    <div class="border p-2 rounded mt-2">
                        <pre class="mb-0" style="white-space: pre-wrap;">${this.escapeHtml(event.notes)}</pre>
                    </div>
                </div>
            ` : ''}
        `;
    }
    
    // Helper to escape HTML for display
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // Set loading state for a button
    setLoadingState(element, loading = true) {
        if (!element) return;
        if (loading) {
            element.disabled = true;
            // Store original HTML for submit button if not already stored
            if (!element.dataset.originalHtml) {
                element.dataset.originalHtml = element.innerHTML;
            }
            element.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>กำลังประมวลผล...';
        } else {
            element.disabled = false;
            // Restore original HTML
            element.innerHTML = element.dataset.originalHtml || element.innerHTML;
        }
    }
    
    clearFormErrors(form) {
        form.querySelectorAll('.is-invalid').forEach(field => {
            field.classList.remove('is-invalid');
        });
        
        form.querySelectorAll('.invalid-feedback').forEach(feedback => {
            feedback.textContent = '';
        });

        // Also clear custom 'field-error' divs if present
        form.querySelectorAll('.field-error').forEach(div => {
            div.textContent = '';
        });
    }
    
    // Notification system
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
    
    showFallbackNotification(message, type, settings) {
        const defaults = { duration: 5000, position: 'top-right', closable: true };
        settings = { ...defaults, ...settings };

        const notification = document.createElement('div');
        notification.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
        notification.style.cssText = `
            top: 20px; 
            right: 20px; 
            z-index: 9999; 
            min-width: 300px;
            max-width: 500px;
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
    
    // Subscription monitoring
    initializeSubscriptionMonitoring() {
        // Ensure currentOrganization is loaded before checking
        if (!this.state.currentOrganization && this.state.currentUser) {
            // Attempt to load organization data if not already present
            // (e.g., from a meta tag or initial API call)
            // For now, if it's null, we just skip.
            this.log('debug', 'No currentOrganization data for subscription monitoring.');
            return; 
        } else if (!this.state.currentOrganization) {
            return; // No user, no organization
        }
        
        this.checkTrialStatus();
        this.checkSubscriptionStatus();
        
        setInterval(() => {
            this.checkTrialStatus();
            this.checkSubscriptionStatus();
        }, 300000); // Every 5 minutes
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
        
        if (lastShown && (now - parseInt(lastShown)) < (1 * 60 * 60 * 1000)) { // 1 hour
            return;
        }
        
        this.showNotification(
            `การทดลองใช้จะหมดอายุในอีก ${daysLeft} วัน กรุณาเลือกแพ็คเกจเพื่อใช้งานต่อ`,
            'warning',
            { duration: 10000 }
        );
        
        localStorage.setItem('trial_warning_shown', now.toString());
    }
    
    showTrialExpired() {
        this.showNotification(
            'การทดลองใช้หมดอายุแล้ว ฟีเจอร์บางอย่างอาจถูกจำกัด',
            'error',
            { duration: 0 } // Don't auto-dismiss
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
        document.querySelectorAll('form').forEach(form => {
            form.addEventListener('submit', (event) => {
                event.preventDefault(); // Prevent default submission
                this.showUpgradeModal('suspended');
            });
        });
        this.showNotification('บัญชีของคุณถูกระงับการใช้งาน กรุณาอัพเกรดแพ็คเกจ', 'error', { duration: 0 });
    }
    
    handleCancelledAccount() {
        this.showNotification(
            'การสมัครสมาชิกถูกยกเลิกแล้ว คุณจะใช้งานได้ถึงวันหมดอายุ',
            'info',
            { duration: 8000 }
        );
    }
    
    // Usage limits monitoring
    initializeUsageLimits() {
        this.checkUsageLimits();
        
        setInterval(() => {
            this.checkUsageLimits();
        }, 120000); // Every 2 minutes
    }
    
    async checkUsageLimits() {
        try {
            const response = await this.httpRequest('/api/usage-stats');
            
            if (response.success && response.data) {
                // Update internal state
                this.state.currentOrganization.max_appointments_per_month = response.data.max_appointments;
                this.state.currentOrganization.max_staff_users = response.data.max_staff;
                this.state.currentOrganization.can_create_appointment = response.data.can_create_appointment;
                this.state.currentOrganization.can_add_staff = response.data.can_add_staff;

                // Update UI elements on the dashboard (if present)
                this.updateUsageIndicators(response.data);

                if (!response.data.can_create_appointment) {
                    this.showNotification(
                        `คุณใช้งานนัดหมายครบ ${response.data.monthly_appointments} รายการแล้ว (${response.data.max_appointments} คือขีดจำกัด). กรุณาอัปเกรดแพ็คเกจ.`,
                        'warning',
                        { duration: 0 } // Sticky warning
                    );
                } else if (!response.data.can_add_staff) {
                     this.showNotification(
                        `คุณใช้งานเจ้าหน้าที่ครบ ${response.data.monthly_staff} รายการแล้ว (${response.data.max_staff} คือขีดจำกัด). กรุณาอัปเกรดแพ็คเกจ.`,
                        'warning',
                        { duration: 0 } // Sticky warning
                    );
                }
            }
            
        } catch (error) {
            this.log('warn', 'Failed to check usage limits:', error);
            // Show notification if API is unreachable or returns critical error
            this.showNotification('ไม่สามารถตรวจสอบขีดจำกัดการใช้งานได้', 'warning', { duration: 5000 });
        }
    }
    
    updateUsageIndicators(data) {
        // Find dashboard elements and update them
        const apptUsageText = document.querySelector('.usage-appointments-text');
        if (apptUsageText) {
            apptUsageText.textContent = `${data.monthly_appointments} / ${data.max_appointments === -1 ? '∞' : data.max_appointments}`;
        }
        
        const apptProgressBar = document.querySelector('.usage-appointments-progress .progress-bar');
        if (apptProgressBar && data.max_appointments > 0) {
            const percentage = (data.monthly_appointments / data.max_appointments) * 100;
            apptProgressBar.style.width = `${Math.min(percentage, 100)}%`;
            apptProgressBar.className = `progress-bar ${this.getProgressBarClass(percentage)}`;
        }

        const staffUsageText = document.querySelector('.usage-staff-text');
        if (staffUsageText) {
            staffUsageText.textContent = `${data.monthly_staff || 0} / ${data.max_staff === -1 ? '∞' : data.max_staff}`;
        }

        const staffProgressBar = document.querySelector('.usage-staff-progress .progress-bar');
        if (staffProgressBar && data.max_staff > 0) {
            const percentage = ((data.monthly_staff || 0) / data.max_staff) * 100;
            staffProgressBar.style.width = `${Math.min(percentage, 100)}%`;
            staffProgressBar.className = `progress-bar ${this.getProgressBarClass(percentage)}`;
        }
    }
    
    getProgressBarClass(percentage) {
        if (percentage >= 90) return 'bg-danger';
        if (percentage >= 80) return 'bg-warning';
        return 'bg-success';
    }
    
    showUpgradeModal(reason) {
        const modalElement = document.getElementById('upgradeModal'); // Assuming a pre-existing modal
        if (!modalElement) { // If modal doesn't exist, create it dynamically
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = `
                <div class="modal fade" id="upgradeModal" tabindex="-1" aria-hidden="true">
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header bg-warning text-dark">
                                <h5 class="modal-title">
                                    <i class="fas fa-exclamation-triangle"></i> 
                                    ${reason === 'suspended' ? 'บัญชีถูกระงับ' : 'ถึงขีดจำกัดการใช้งาน'}
                                </h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body">
                                ${this.getUpgradeModalContent(reason)}
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">ปิด</button>
                                <a href="/billing/choose-plan" class="btn btn-warning">อัพเกรดเลย</a>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            document.body.appendChild(tempDiv.firstElementChild);
            modalElement = document.getElementById('upgradeModal');
        }

        const bootstrapModal = new bootstrap.Modal(modalElement);
        bootstrapModal.show();
        
        modalElement.addEventListener('hidden.bs.modal', () => {
            // modalElement.remove(); // Only remove if dynamically created
        });
    }
    
    getUpgradeModalContent(reason) {
        switch (reason) {
            case 'suspended':
                return '<p>บัญชีของคุณถูกระงับการใช้งาน กรุณาอัพเกรดแพ็คเกจหรือติดต่อผู้ดูแลระบบ</p>';
            case 'appointments':
                return '<p>คุณได้ใช้งานนัดหมายครบตามแพ็คเกจแล้ว กรุณาอัพเกรดแพ็คเกจเพื่อใช้งานต่อ</p>';
            case 'staff':
                return '<p>คุณได้เพิ่มเจ้าหน้าที่ครบตามแพ็คเกจแล้ว กรุณาอัพเกรดแพ็คเกจเพื่อเพิ่มเจ้าหน้าที่</p>';
            default:
                return '<p>กรุณาอัพเกรดแพ็คเกจเพื่อใช้งานต่อ</p>';
        }
    }
    
    // Error handling and reporting
    setupErrorHandling() {
        this.setupGlobalErrorHandlers();
        this.setupErrorReporting();
    }
    
    setupGlobalErrorHandlers() {
        // Already set up in setupEventListeners
    }
    
    setupErrorReporting() {
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
        
        this.errorQueue.push(errorReport);
        
        if (this.errorQueue.length > this.maxErrorQueueSize) {
            this.errorQueue.shift();
        }
        
        this.sendErrorReport(errorReport);
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
    
    // Keyboard shortcuts
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
            const newTab = document.querySelector('#new-tab');
            if (newTab && !newTab.disabled) {
                newTab.click();
            }
        }
        
        if (event.key === 'Escape') {
            const openModal = document.querySelector('.modal.show');
            if (openModal) {
                const modal = bootstrap.Modal.getInstance(openModal);
                if (modal) {
                    modal.hide();
                }
            }
        }
    }
    
    // Form handling utilities (already integrated into handleAsyncForm)
    handleFormSuccess(form, response) {
        form.reset();
        this.updateFormToken(form, response.new_form_token); // Pass new token
        
        if (response.redirect_url) {
            setTimeout(() => {
                window.location.href = response.redirect_url;
            }, 1000);
        }
        
        if (form.dataset.refreshTarget) {
            this.refreshComponent(form.dataset.refreshTarget);
        }
    }
    
    handleFormError(form, error) {
        this.showNotification(error.message || 'เกิดข้อผิดพลาดในการส่งข้อมูล', 'error');
        this.updateFormToken(form, error.new_form_token); // Pass new token from error response
        
        if (error.field_errors) {
            Object.keys(error.field_errors).forEach(fieldName => {
                const field = form.querySelector(`[name="${fieldName}"]`);
                if (field) {
                    this.showFieldError(field, error.field_errors[fieldName]);
                }
            });
        }
    }
    
    updateFormToken(form, newToken = null) {
        const tokenField = form.querySelector('input[name="form_token"]');
        if (tokenField) {
            tokenField.value = newToken || this.generateFormToken(); // Use provided token or generate new one
        }
    }
    
    refreshComponent(target) {
        switch (target) {
            case 'appointments':
                this.loadAppointments({}); // Refresh with default filters
                break;
            case 'usage':
                this.checkUsageLimits();
                break;
            default:
                window.location.reload();
        }
    }
    
    // Heartbeat and connection monitoring
    startHeartbeat() {
        this.heartbeatInterval = setInterval(() => {
            this.sendHeartbeat();
        }, 60000);
    }
    
    async sendHeartbeat() {
        try {
            await this.httpRequest('/api/heartbeat', {
                method: 'POST',
                body: JSON.stringify({
                    timestamp: Date.now(),
                    page: window.location.pathname
                })
            });
            this.log('debug', 'Heartbeat sent.');
        } catch (error) {
            this.log('warn', 'Heartbeat failed:', error);
            this.handleConnectionLoss();
        }
    }
    
    handleConnectionLoss() {
        this.showNotification(
            'การเชื่อมต่อขาดหาย กำลังพยายามเชื่อมต่อใหม่...',
            'warning',
            { duration: 0 }
        );
    }
    
    // Lifecycle management
    pauseOperations() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
        }
    }
    
    resumeOperations() {
        this.startHeartbeat();
        this.checkUsageLimits();
    }
    
    async syncPendingData() {
        try {
            const pendingForms = JSON.parse(localStorage.getItem('pending_forms') || '[]');
            
            for (const formData of pendingForms) {
                try {
                    await this.httpRequest(formData.action, {
                        method: formData.method,
                        body: formData.data
                    });
                } catch (error) {
                    this.log('warn', 'Failed to sync pending form:', error);
                }
            }
            
            localStorage.removeItem('pending_forms');
            
        } catch (error) {
            this.log('error', 'Failed to sync pending data:', error);
        }
    }
    
    // Authorization handling
    handleUnauthorized() {
        this.showNotification('กรุณาเข้าสู่ระบบใหม่', 'warning');
        setTimeout(() => {
            window.location.href = '/auth/login';
        }, 2000);
    }
    
    // Public API methods for direct access from templates (e.g., onclick="window.app.showEventDetails('ID')")
    // These functions should only call the internal class methods.

    // No need to define createAppointment here if it's handled by handleAsyncForm globally
    // createAppointment(formData) is no longer required as a public method directly exposed.
    // The handleAsyncForm already takes care of the submission logic.
    
    // showEventDetails is already a public method of window.app due to the class instance assignment.
    // No explicit public declaration needed here.

    // checkUsageLimits is also accessible via window.app.checkUsageLimits
    // getCSRFToken is accessible via window.app.getCSRFToken
    // httpRequest is accessible via window.app.httpRequest

    // Expose utility functions if needed directly in HTML
    // window.app.escapeHtml = this.escapeHtml; // Not strictly necessary if always called via this.
    
    // Cleanup
    destroy() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
        }
        
        this.eventHandlers.clear();
        this.state.eventsCache.clear();
        this.state.formTokens.clear();
    }
}

// Global initialization of the app
// This makes the app instance accessible via `window.app`
document.addEventListener('DOMContentLoaded', function() {
    try {
        window.app = new NudDeeSaaSApp(); // Assign the instance to window.app directly
    } catch (error) {
        console.error('Failed to initialize NudDee SaaS App:', error);
        
        // Fallback notification for critical startup errors
        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert alert-danger position-fixed';
        alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 9999;';
        alertDiv.textContent = 'เกิดข้อผิดพลาดร้ายแรงในการเริ่มต้นระบบ กรุณารีเฟรชหน้าเว็บ';
        document.body.appendChild(alertDiv);
    }
});

// For Moment.js usage in templates like dashboard.html:
// Ensure that moment.js and its locale are loaded before any script attempts to use `moment()`.
// base.html now correctly loads moment.js before script.js and any block scripts.