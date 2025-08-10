// static/js/app.js

document.addEventListener('DOMContentLoaded', () => {
    const token = localStorage.getItem('accessToken');

    // --- Page Routing Logic ---
    // If not logged in and tries to access dashboard, redirect to login
    if (!token && window.location.pathname.startsWith('/dashboard')) {
        window.location.href = '/';
        return;
    }
    
    // If logged in and on the login page, redirect to dashboard
    if (token && window.location.pathname === '/') {
        window.location.href = '/dashboard';
        return;
    }

    // --- Logic for Dashboard Page ---
    if (window.location.pathname.startsWith('/dashboard')) {
        initializeDashboard(token);
    }

    // --- Logic for Login/Register Page ---
    if (window.location.pathname === '/') {
        initializeLoginPage();
    }
});

/**
 * Initializes all functionalities for the dashboard page.
 */
function initializeDashboard(token) {
    // Initialize Semantic UI tabs
    $('.menu .item').tab();

    // Load initial data
    loadBookings(token);

    // Setup event listeners for buttons and forms
    document.getElementById('logout-btn').addEventListener('click', () => {
        localStorage.removeItem('accessToken');
        window.location.href = '/';
    });

    document.getElementById('settings-form').addEventListener('submit', (e) => handleSaveApiKey(e, token));
    document.getElementById('new-booking-btn').addEventListener('click', () => handleNewBookingClick(token));
    document.getElementById('new-booking-form').addEventListener('submit', (e) => handleCreateBookingSubmit(e, token));
}

/**
 * Initializes all functionalities for the login page.
 */
function initializeLoginPage() {
    document.getElementById('login-form').addEventListener('submit', handleLoginSubmit);
    document.getElementById('show-register').addEventListener('click', (e) => {
        e.preventDefault();
        $('.ui.modal#register-modal').modal('show');
    });
    document.getElementById('register-form').addEventListener('submit', handleRegisterSubmit);
}

// --- Handler Functions ---

async function handleLoginSubmit(e) {
    e.preventDefault();
    const formData = new FormData(e.target);
    try {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        if (response.ok) {
            localStorage.setItem('accessToken', data.access_token);
            window.location.href = '/dashboard';
        } else {
            alert(`Login failed: ${data.detail}`);
        }
    } catch (error) {
        console.error('Login error:', error);
    }
}

async function handleRegisterSubmit(e) {
    e.preventDefault();
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData.entries());
    try {
        const response = await fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        if (response.ok) {
            alert('Registration successful! You can now log in.');
            $('.ui.modal#register-modal').modal('hide');
            e.target.reset();
        } else {
            alert(`Registration failed: ${result.detail}`);
        }
    } catch (error) {
        console.error('Registration error:', error);
        alert('An error occurred during registration.');
    }
}

async function handleSaveApiKey(e, token) {
    e.preventDefault();
    const apiKey = document.getElementById('api-key-input').value;
    if (!apiKey) {
        alert('Please enter an API Key.');
        return;
    }
    try {
        const response = await fetch('/api/organization/api_key', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ api_key: apiKey })
        });
        const result = await response.json();
        if (response.ok) {
            alert('API Key saved successfully!');
        } else {
            alert(`Failed to save API Key: ${result.detail}`);
        }
    } catch (error) {
        alert('An error occurred while saving the API Key.');
    }
}

async function handleNewBookingClick(token) {
    const eventTypeDropdown = document.getElementById('event-type-dropdown');
    try {
        const response = await fetch('/api/organization/event-types', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.status === 403) {
             throw new Error('Could not fetch event types. Have you saved your API Key in Settings?');
        }
        if (!response.ok) throw new Error('An unknown error occurred fetching event types.');

        const eventTypes = await response.json();
        eventTypeDropdown.innerHTML = '<option value="">Select Event Type</option>';
        eventTypes.forEach(et => {
            eventTypeDropdown.innerHTML += `<option value="${et.id}">${et.title}</option>`;
        });
        $('.ui.modal#new-booking-modal').modal('show');
    } catch (error) {
        alert(error.message);
    }
}

async function handleCreateBookingSubmit(e, token) {
    e.preventDefault();
    const formData = new FormData(e.target);
    const startTime = new Date(formData.get('start')).toISOString();
    const endTime = new Date(formData.get('end')).toISOString();
    const data = {
        title: formData.get('title'),
        start: startTime,
        end: endTime,
        eventTypeId: parseInt(formData.get('eventTypeId')),
        description: formData.get('description'),
        responses: {} // Placeholder for custom fields
    };
    try {
        const response = await fetch('/api/bookings/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        if (response.ok) {
            alert('Booking created successfully!');
            $('.ui.modal#new-booking-modal').modal('hide');
            e.target.reset();
            loadBookings(token); // Refresh the booking list
        } else {
            alert(`Failed to create booking: ${JSON.stringify(result.detail)}`);
        }
    } catch (error) {
        alert('An error occurred while creating the booking.');
    }
}

/**
 * Fetches and displays bookings on the dashboard.
 */
async function loadBookings(token) {
    const bookingList = document.getElementById('booking-list');
    bookingList.innerHTML = '<div class="ui active centered inline loader"></div>';
    try {
        const response = await fetch('/api/bookings/', {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.status === 403) {
            bookingList.innerHTML = `<div class="ui warning message"><div class="header">API Key is required</div><p>Please go to the "Settings" tab and save your Cal.com API Key.</p></div>`;
            return;
        }

        if (!response.ok) {
            const errorData = await response.json();
            const errorDetail = JSON.stringify(errorData.detail, null, 2);
            bookingList.innerHTML = `<div class="ui error message"><div class="header">Error Loading Bookings (${response.status})</div><p>The Cal.com API returned an error:</p><pre>${errorDetail}</pre></div>`;
            return;
        }

        const bookings = await response.json();
        if (bookings.length === 0) {
            bookingList.innerHTML = '<div class="ui info message"><p>No bookings found.</p></div>';
            return;
        }

        const cardsContainer = document.createElement('div');
        cardsContainer.className = 'ui cards';
        bookings.forEach(booking => {
            const card = `
                <div class="card">
                    <div class="content">
                        <div class="header">${booking.title}</div>
                        <div class="meta">${booking.organizer?.name || 'N/A'}</div>
                        <div class="description">
                            <p><i class="calendar alternate outline icon"></i>${new Date(booking.startTime).toLocaleString('th-TH', { dateStyle: 'full', timeStyle: 'short' })}</p>
                            <p><i class="info circle icon"></i>Status: <span class="ui ${booking.status === 'CONFIRMED' ? 'green' : 'grey'} tiny label">${booking.status}</span></p>
                        </div>
                    </div>
                    <div class="extra content">
                        <div class="ui two buttons">
                            <button class="ui basic green button">Details</button>
                            <button class="ui basic red button">Cancel</button>
                        </div>
                    </div>
                </div>`;
            cardsContainer.insertAdjacentHTML('beforeend', card);
        });
        bookingList.innerHTML = '';
        bookingList.appendChild(cardsContainer);
    } catch (error) {
        console.error('Failed to load bookings:', error);
        bookingList.innerHTML = '<div class="ui error message"><p>Error connecting to the server.</p></div>';
    }
}