-- ใน psql console
SET search_path TO tenant_humnoi, public;

-- 1. สร้าง tables ใหม่ที่จำเป็น
CREATE TABLE event_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    duration_minutes INTEGER NOT NULL DEFAULT 15,
    color VARCHAR(7) DEFAULT '#6366f1',
    is_active BOOLEAN DEFAULT TRUE,
    buffer_before_minutes INTEGER DEFAULT 0,
    buffer_after_minutes INTEGER DEFAULT 0,
    max_bookings_per_day INTEGER,
    min_notice_hours INTEGER DEFAULT 4,
    max_advance_days INTEGER DEFAULT 60,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE service_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE providers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    title VARCHAR(50),
    department VARCHAR(100),
    email VARCHAR(120),
    phone VARCHAR(20),
    is_active BOOLEAN DEFAULT TRUE,
    public_booking_url VARCHAR(100) UNIQUE,
    bio TEXT,
    profile_image_url VARCHAR(255)
);

-- 2. อัปเดต appointments table
ALTER TABLE appointments ADD COLUMN provider_id INTEGER;
ALTER TABLE appointments ADD COLUMN event_type_id INTEGER;
ALTER TABLE appointments ADD COLUMN service_type_id INTEGER;
ALTER TABLE appointments ADD COLUMN booking_reference VARCHAR(20) UNIQUE;
ALTER TABLE appointments ADD COLUMN status VARCHAR(20) DEFAULT 'confirmed';
ALTER TABLE appointments ADD COLUMN guest_name VARCHAR(100);
ALTER TABLE appointments ADD COLUMN guest_email VARCHAR(120);
ALTER TABLE appointments ADD COLUMN guest_phone VARCHAR(20);
ALTER TABLE appointments ADD COLUMN internal_notes TEXT;
ALTER TABLE appointments ADD COLUMN reminder_sent BOOLEAN DEFAULT FALSE;
ALTER TABLE appointments ADD COLUMN reminder_sent_at TIMESTAMP;
ALTER TABLE appointments ADD COLUMN cancelled_at TIMESTAMP;
ALTER TABLE appointments ADD COLUMN cancelled_by VARCHAR(50);
ALTER TABLE appointments ADD COLUMN cancellation_reason TEXT;
ALTER TABLE appointments ADD COLUMN rescheduled_from_id INTEGER;
ALTER TABLE appointments ADD COLUMN reschedule_count INTEGER DEFAULT 0;
ALTER TABLE appointments ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- 3. เพิ่ม Foreign Keys
ALTER TABLE appointments ADD CONSTRAINT fk_appointments_provider 
    FOREIGN KEY (provider_id) REFERENCES providers(id);
ALTER TABLE appointments ADD CONSTRAINT fk_appointments_event_type 
    FOREIGN KEY (event_type_id) REFERENCES event_types(id);
ALTER TABLE appointments ADD CONSTRAINT fk_appointments_service_type 
    FOREIGN KEY (service_type_id) REFERENCES service_types(id);

-- 4. เพิ่มข้อมูลเริ่มต้น
INSERT INTO event_types (name, slug, description, duration_minutes, color) VALUES 
('15 Min Meeting', '15min', 'การนัดหมายสั้น 15 นาที', 15, '#6366f1'),
('30 Min Consultation', '30min', 'การปรึกษา 30 นาที', 30, '#059669'),
('Health Screening', 'screening', 'ตรวจสุขภาพทั่วไป', 60, '#dc2626');

INSERT INTO service_types (name, description) VALUES 
('general', 'ตรวจรักษาทั่วไป'),
('vaccination', 'ฉีดวัคซีน'),
('screening', 'ตรวจสุขภาพ'),
('consultation', 'ปรึกษาปัญหาสุขภาพ');

INSERT INTO providers (name, title, department, public_booking_url, bio) VALUES 
('สมชาย ใจดี', 'นพ.', 'เวชศาสตร์ครอบครัว', 'dr-somchai', 'แพทย์เวชศาสตร์ครอบครัวที่มีประสบการณ์กว่า 10 ปี');

-- 5. อัปเดต appointments ที่มีอยู่ (ถ้ามี)
UPDATE appointments SET 
    provider_id = 1,  -- ใช้ provider แรก
    event_type_id = 1,  -- ใช้ event type แรก
    service_type_id = 1,  -- ใช้ service type แรก
    status = 'confirmed'
WHERE provider_id IS NULL;