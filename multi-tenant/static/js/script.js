// static/js/script.js - Production-ready JavaScript

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
            formTokens: new Set()
        };
        
        this.eventHandlers = new Map();
        this.init();
    }
    
    init() {
        try {
            this.loadUserContext();
            this.setupEventListeners();
            this.initializeComponents();
            this.setupErrorHandling();
            this.startHeartbeat();
            
            this.log('info', 'NudDee SaaS App initialized successfully');
        } catch (error) {
            this.log('error', 'Failed to initialize app:', error);
            this.showNotification('เกิดข้อผิดพลาดในการเริ่มต้นระบบ', 'error');
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
                
                if (attempt === this.config.retryAttempts) {
                    throw error;
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
        const token = document.querySelector('meta[name="csrf-token"]');
        return token ? token.getAttribute('content') : '';
    }
    
    generateFormToken() {
        return crypto.randomUUID ? crypto.randomUUID() : this.generateUUID();
    }
    
    generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            const r = Math.random() * 16 | 0;
            const v = c == 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }
    
    // User context management
    loadUserContext() {
        try {
            const userMeta = document.querySelector('meta[name="current-user"]');
            const orgMeta = document.querySelector('meta[name="current-organization"]');
            
            if (userMeta) {
                this.state.currentUser = JSON.parse(userMeta.content);
            }
            
            if (orgMeta) {
                this.state.currentOrganization = JSON.parse(orgMeta.content);
            }
            
            this.log('debug', 'User context loaded:', this.state);
        } catch (error) {
            this.log('warn', 'Failed to load user context:', error);
        }
    }
    
    // Event handling system
    setupEventListeners() {
        // Global error handler
        window.addEventListener('error', (event) => {
            this.log('error', 'Global error:', event.error);
            this.reportError(event.error);
        });
        
        // Unhandled promise rejection
        window.addEventListener('unhandledrejection', (event) => {
            this.log('error', 'Unhandled promise rejection:', event.reason);
            this.reportError(event.reason);
        });
        
        // Network status
        window.addEventListener('online', () => {
            this.showNotification('เชื่อมต่ออินเทอร์เน็ตแล้ว', 'success');
            this.syncPendingData();
        });
        
        window.addEventListener('offline', () => {
            this.showNotification('ขาดการเชื่อมต่ออินเทอร์เน็ต', 'warning');
        });
        
        // Page visibility for cleanup
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.pauseOperations();
            } else {
                this.resumeOperations();
            }
        });
        
        // Keyboard shortcuts
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
        // Auto-focus first input in modals
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
        // Enhanced form handling
        document.querySelectorAll('form[data-async="true"]').forEach(form => {
            form.addEventListener('submit', (event) => {
                this.handleAsyncForm(event);
            });
        });
        
        // Auto-save functionality
        document.querySelectorAll('form[data-autosave="true"]').forEach(form => {
            this.setupAutoSave(form);
        });
        
        // Form validation
        document.querySelectorAll('form[data-validate="true"]').forEach(form => {
            this.setupFormValidation(form);
        });
    }
    
    // Async form handling
    async handleAsyncForm(event) {
        event.preventDefault();
        
        const form = event.target;
        const submitButton = form.querySelector('button[type="submit"]');
        const formData = new FormData(form);
        
        try {
            // Prevent duplicate submissions
            const formToken = formData.get('form_token');
            if (formToken && this.state.formTokens.has(formToken)) {
                this.showNotification('กำลังประมวลผลคำขออยู่', 'info');
                return;
            }
            
            if (formToken) {
                this.state.formTokens.add(formToken);
            }
            
            // Set loading state
            this.setLoadingState(submitButton, true);
            
            // Clear previous errors
            this.clearFormErrors(form);
            
            // Submit form
            const response = await this.httpRequest(form.action, {
                method: form.method || 'POST',
                body: formData
            });
            
            if (response.success) {
                this.showNotification('บันทึกข้อมูลสำเร็จ', 'success');
                this.handleFormSuccess(form, response);
            } else {
                throw new Error(response.error || 'Form submission failed');
            }
            
        } catch (error) {
            this.log('error', 'Form submission error:', error);
            this.handleFormError(form, error);
        } finally {
            this.setLoadingState(submitButton, false);
            
            // Remove form token after processing
            const formToken = formData.get('form_token');
            if (formToken) {
                setTimeout(() => {
                    this.state.formTokens.delete(formToken);
                }, 5000);
            }
        }
    }
    
    // Form validation
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
            rules.push({
                validate: (value) => !value || value.length >= 8,
                message: 'รหัสผ่านต้องมีอย่างน้อย 8 ตัวอักษร'
            });
        }
        
        if (field.dataset.minLength) {
            const minLength = parseInt(field.dataset.minLength);
            rules.push({
                validate: (value) => !value || value.length >= minLength,
                message: `ต้องมีอย่างน้อย ${minLength} ตัวอักษร`
            });
        }
        
        if (field.dataset.maxLength) {
            const maxLength = parseInt(field.dataset.maxLength);
            rules.push({
                validate: (value) => !value || value.length <= maxLength,
                message: `ต้องไม่เกิน ${maxLength} ตัวอักษร`
            });
        }
        
        return rules;
    }
    
    showFieldError(field, message) {
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
        field.classList.remove('is-invalid');
        field.classList.add('is-valid');
        
        const errorDiv = field.parentNode.querySelector('.invalid-feedback');
        if (errorDiv) {
            errorDiv.textContent = '';
        }
    }
    
    // Auto-save functionality
    setupAutoSave(form) {
        const formId = form.id || `form_${Date.now()}`;
        let saveTimeout;
        
        // Load saved data
        this.loadAutoSavedData(form, formId);
        
        // Save on input
        form.addEventListener('input', () => {
            clearTimeout(saveTimeout);
            saveTimeout = setTimeout(() => {
                this.saveFormData(form, formId);
            }, 2000);
        });
        
        // Clear on successful submit
        form.addEventListener('submit', () => {
            this.clearAutoSavedData(formId);
        });
    }
    
    saveFormData(form, formId) {
        try {
            const formData = new FormData(form);
            const data = Object.fromEntries(formData);
            
            // Remove sensitive data
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
        // Small, unobtrusive notification
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
    
    // Appointment management
    async loadAppointments(filters = {}) {
        try {
            const params = new URLSearchParams(filters);
            const cacheKey = params.toString();
            
            // Check cache first
            if (this.state.eventsCache.has(cacheKey)) {
                const cached = this.state.eventsCache.get(cacheKey);
                if (Date.now() - cached.timestamp < 60000) { // 1 minute cache
                    this.displayAppointments(cached.data);
                    return;
                }
            }
            
            const response = await this.httpRequest(`/get_events?${params}`);
            
            // Cache the response
            this.state.eventsCache.set(cacheKey, {
                data: response,
                timestamp: Date.now()
            });
            
            this.displayAppointments(response);
            
        } catch (error) {
            this.log('error', 'Failed to load appointments:', error);
            this.showNotification('ไม่สามารถโหลดรายการนัดหมายได้', 'error');
        }
    }
    
    displayAppointments(data) {
        const container = document.getElementById('appointments-container');
        if (!container) return;
        
        if (!data.events || data.events.length === 0) {
            container.innerHTML = `
                <div class="alert alert-info">
                    <i class="fas fa-info-circle me-2"></i>ไม่พบรายการนัดหมายในช่วงเวลาที่เลือก
                </div>
            `;
            return;
        }
        
        // Group events by date
        const eventsByDate = this.groupEventsByDate(data.events);
        
        container.innerHTML = '';
        
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
        if (event.title.includes('(มาตามนัด)')) {
            statusClass = 'border-success';
        } else if (event.title.includes('(ยกเลิก)')) {
            statusClass = 'border-danger';
        } else if (event.title.includes('(ไม่มา)')) {
            statusClass = 'border-warning';
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
                    <a href="/update_status?event_id=${event.id}" class="btn btn-sm btn-primary">
                        <i class="fas fa-edit me-1"></i>อัปเดตสถานะ
                    </a>
                    <button class="btn btn-sm btn-outline-secondary" onclick="app.showEventDetails('${event.id}')">
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
            const response = await this.httpRequest(`/get_events?event_id=${eventId}`);
            
            if (!response.events || response.events.length === 0) {
                this.showNotification('ไม่พบข้อมูลนัดหมาย', 'warning');
                return;
            }
            
            const event = response.events[0];
            this.displayEventModal(event);
            
        } catch (error) {
            this.log('error', 'Failed to load event details:', error);
            this.showNotification('ไม่สามารถโหลดรายละเอียดนัดหมายได้', 'error');
        }
    }
    
    displayEventModal(event) {
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">รายละเอียดนัดหมาย</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        ${this.renderEventDetails(event)}
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">ปิด</button>
                        <a href="/update_status?event_id=${event.id}" class="btn btn-primary">
                            <i class="fas fa-edit me-1"></i>อัปเดตสถานะ
                        </a>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        const bootstrapModal = new bootstrap.Modal(modal);
        bootstrapModal.show();
        
        modal.addEventListener('hidden.bs.modal', () => {
            modal.remove();
        });
    }
    
    renderEventDetails(event) {
        const subcalendarDisplay = event.subcalendar_display || 'ไม่ระบุปฏิทิน';
        const startDate = new Date(event.start_dt).toLocaleDateString('th-TH');
        const startTime = event.start_dt.split('T')[1].substring(0, 5);
        const endTime = event.end_dt.split('T')[1].substring(0, 5);
        
        return `
            <div class="row">
                <div class="col-md-8">
                    <h4>${this.escapeHtml(event.title)}</h4>
                    <div class="mb-3">
                        <span class="badge bg-secondary me-2">
                            <i class="fas fa-calendar me-1"></i>${this.escapeHtml(subcalendarDisplay)}
                        </span>
                    </div>
                </div>
                <div class="col-md-4 text-end">
                    <small class="text-muted">Event ID: ${event.id}</small>
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
    
    // Utility functions
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    setLoadingState(element, loading = true) {
        if (loading) {
            element.disabled = true;
            element.dataset.originalText = element.innerHTML;
            element.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>กำลังประมวลผล...';
        } else {
            element.disabled = false;
            element.innerHTML = element.dataset.originalText || element.innerHTML;
        }
    }
    
    clearFormErrors(form) {
        form.querySelectorAll('.is-invalid').forEach(field => {
            field.classList.remove('is-invalid');
        });
        
        form.querySelectorAll('.invalid-feedback').forEach(feedback => {
            feedback.textContent = '';
        });
    }
    
    // Notification system
    showNotification(message, type = 'info', options = {}) {
        const defaults = {
            duration: 5000,
            position: 'top-right',
            closable: true
        };
        
        const settings = { ...defaults, ...options };
        
        if (typeof Swal !== 'undefined') {
            const toast = Swal.mixin({
                toast: true,
                position: settings.position,
                showConfirmButton: false,
                timer: settings.duration,
                timerProgressBar: true,
                didOpen: (toast) => {
                    toast.addEventListener('mouseenter', Swal.stopTimer);
                    toast.addEventListener('mouseleave', Swal.resumeTimer);
                }
            });
            
            toast.fire({
                icon: type === 'error' ? 'error' : type === 'success' ? 'success' : 'info',
                title: message
            });
        } else {
            // Fallback notification
            this.showFallbackNotification(message, type, settings);
        }
    }
    
    showFallbackNotification(message, type, settings) {
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
        if (!this.state.currentOrganization) return;
        
        this.checkTrialStatus();
        this.checkSubscriptionStatus();
        
        // Check every 5 minutes
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
            const daysLeft = Math.ceil((new Date(trialEnds) - new Date()) / (1000 * 60 * 60 * 24));
            
            if (daysLeft <= 3 && daysLeft > 0) {
                this.showTrialWarning(daysLeft);
            } else if (daysLeft <= 0) {
                this.showTrialExpired();
            }
        }
    }
    
    showTrialWarning(daysLeft) {
        // Only show if not already shown recently
        const lastShown = localStorage.getItem('trial_warning_shown');
        const now = Date.now();
        
        if (lastShown && (now - parseInt(lastShown)) < 3600000) { // 1 hour
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
        // Disable form submissions
        document.querySelectorAll('form').forEach(form => {
            form.addEventListener('submit', (event) => {
                event.preventDefault();
                this.showUpgradeModal('suspended');
            });
        });
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
        
        // Check every 2 minutes
        setInterval(() => {
            this.checkUsageLimits();
        }, 120000);
    }
    
    async checkUsageLimits() {
        try {
            const response = await this.httpRequest('/api/usage-stats');
            
            if (response.appointment_usage_percent >= 90) {
                this.showUsageLimitWarning('appointments', response.appointment_usage_percent);
            }
            
            if (response.staff_usage_percent >= 90) {
                this.showUsageLimitWarning('staff', response.staff_usage_percent);
            }
            
            this.updateUsageIndicators(response);
            
        } catch (error) {
            this.log('warn', 'Failed to check usage limits:', error);
        }
    }
    
    showUsageLimitWarning(type, percentage) {
        const typeText = type === 'appointments' ? 'นัดหมาย' : 'เจ้าหน้าที่';
        
        this.showNotification(
            `การใช้งาน${typeText}ถึง ${percentage.toFixed(1)}% แล้ว`,
            'warning',
            { duration: 8000 }
        );
    }
    
    updateUsageIndicators(data) {
        // Update progress bars
        const appointmentProgress = document.querySelector('.usage-appointments .progress-bar');
        if (appointmentProgress) {
            appointmentProgress.style.width = `${data.appointment_usage_percent}%`;
            appointmentProgress.className = `progress-bar ${this.getProgressBarClass(data.appointment_usage_percent)}`;
        }
        
        const staffProgress = document.querySelector('.usage-staff .progress-bar');
        if (staffProgress) {
            staffProgress.style.width = `${data.staff_usage_percent}%`;
            staffProgress.className = `progress-bar ${this.getProgressBarClass(data.staff_usage_percent)}`;
        }
        
        // Update text
        const appointmentText = document.querySelector('.usage-appointments .usage-text');
        if (appointmentText) {
            appointmentText.textContent = `${data.appointments_used} / ${data.appointments_limit || 'ไม่จำกัด'}`;
        }
        
        const staffText = document.querySelector('.usage-staff .usage-text');
        if (staffText) {
            staffText.textContent = `${data.staff_used} / ${data.staff_limit || 'ไม่จำกัด'}`;
        }
    }
    
    getProgressBarClass(percentage) {
        if (percentage >= 90) return 'bg-danger';
        if (percentage >= 80) return 'bg-warning';
        return 'bg-success';
    }
    
    showUpgradeModal(reason) {
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.innerHTML = `
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
        `;
        
        document.body.appendChild(modal);
        
        const bootstrapModal = new bootstrap.Modal(modal);
        bootstrapModal.show();
        
        modal.addEventListener('hidden.bs.modal', () => {
            modal.remove();
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
        // Set up global error boundaries
        this.setupGlobalErrorHandlers();
        
        // Set up error reporting
        this.setupErrorReporting();
    }
    
    setupGlobalErrorHandlers() {
        // Already set up in setupEventListeners
    }
    
    setupErrorReporting() {
        // Could integrate with Sentry, LogRocket, etc.
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
        
        // Add to queue
        this.errorQueue.push(errorReport);
        
        // Keep queue size manageable
        if (this.errorQueue.length > this.maxErrorQueueSize) {
            this.errorQueue.shift();
        }
        
        // Send to server (if configured)
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
        // Ctrl/Cmd + K = Quick search
        if ((event.ctrlKey || event.metaKey) && event.key === 'k') {
            event.preventDefault();
            const searchInput = document.querySelector('#quickSearch');
            if (searchInput) {
                searchInput.focus();
            }
        }
        
        // Ctrl/Cmd + N = New appointment
        if ((event.ctrlKey || event.metaKey) && event.key === 'n') {
            event.preventDefault();
            const newTab = document.querySelector('#new-tab');
            if (newTab && !newTab.disabled) {
                newTab.click();
            }
        }
        
        // Escape = Close modals
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
    
    // Form handling utilities
    handleFormSuccess(form, response) {
        // Reset form
        form.reset();
        
        // Update form token
        this.updateFormToken(form);
        
        // Handle specific success actions
        if (response.redirect_url) {
            setTimeout(() => {
                window.location.href = response.redirect_url;
            }, 1000);
        }
        
        // Refresh data if needed
        if (form.dataset.refreshTarget) {
            this.refreshComponent(form.dataset.refreshTarget);
        }
    }
    
    handleFormError(form, error) {
        this.showNotification(error.message || 'เกิดข้อผิดพลาดในการส่งข้อมูล', 'error');
        
        // Update form token
        this.updateFormToken(form);
        
        // Show field errors if available
        if (error.field_errors) {
            Object.keys(error.field_errors).forEach(fieldName => {
                const field = form.querySelector(`[name="${fieldName}"]`);
                if (field) {
                    this.showFieldError(field, error.field_errors[fieldName]);
                }
            });
        }
    }
    
    updateFormToken(form) {
        const tokenField = form.querySelector('input[name="form_token"]');
        if (tokenField) {
            tokenField.value = this.generateFormToken();
        }
    }
    
    refreshComponent(target) {
        switch (target) {
            case 'appointments':
                this.loadAppointments();
                break;
            case 'usage':
                this.checkUsageLimits();
                break;
            default:
                // Generic refresh
                window.location.reload();
        }
    }
    
    // Heartbeat and connection monitoring
    startHeartbeat() {
        this.heartbeatInterval = setInterval(() => {
            this.sendHeartbeat();
        }, 60000); // Every minute
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
        // Pause background operations when page is hidden
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
        }
    }
    
    resumeOperations() {
        // Resume operations when page becomes visible
        this.startHeartbeat();
        this.checkUsageLimits();
    }
    
    // Data synchronization
    async syncPendingData() {
        // Sync any pending data when connection is restored
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
            
            // Clear pending data
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
    
    // Public API methods
    // These methods can be called from other scripts or inline event handlers
    
    async createAppointment(formData) {
        try {
            const response = await this.httpRequest('/create_appointment', {
                method: 'POST',
                body: formData
            });
            
            if (response.success) {
                this.showNotification('สร้างนัดหมายสำเร็จ', 'success');
                this.loadAppointments(); // Refresh appointments list
                return true;
            } else {
                throw new Error(response.error);
            }
        } catch (error) {
            this.showNotification(error.message, 'error');
            return false;
        }
    }
    
    // Cleanup
    destroy() {
        // Clean up intervals
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
        }
        
        // Clear event listeners
        this.eventHandlers.clear();
        
        // Clear caches
        this.state.eventsCache.clear();
        this.state.formTokens.clear();
    }
}

// Initialize the application
let app;

document.addEventListener('DOMContentLoaded', function() {
    try {
        app = new NudDeeSaaSApp();
        
        // Make app globally available for debugging
        if (window.DEBUG) {
            window.app = app;
        }
        
    } catch (error) {
        console.error('Failed to initialize NudDee SaaS App:', error);
        
        // Fallback notification
        const alert = document.createElement('div');
        alert.className = 'alert alert-danger position-fixed';
        alert.style.cssText = 'top: 20px; right: 20px; z-index: 9999;';
        alert.textContent = 'เกิดข้อผิดพลาดในการเริ่มต้นระบบ กรุณารีเฟรชหน้าเว็บ';
        document.body.appendChild(alert);
    }
});

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = NudDeeSaaSApp;
}