# คู่มือการใช้งานระบบนัดหมายฟอกไตสำหรับการติดตั้งบนเซิร์ฟเวอร์ (Production Guide)

## 1. ภาพรวมระบบ

ระบบนัดหมายฟอกไตเป็นเว็บแอปพลิเคชันที่พัฒนาด้วย Python Flask เชื่อมต่อกับ TeamUp Calendar API เพื่อจัดการนัดหมายฟอกไต โดยมีฟังก์ชันหลักดังนี้:

- การเชื่อมต่อและตั้งค่า TeamUp Calendar API
- การจัดการปฏิทินย่อยสำหรับแต่ละเครื่องฟอกไต
- การสร้างนัดหมายฟอกไตแบบครั้งเดียวและแบบเกิดซ้ำ
- การอัปเดตสถานะนัดหมาย (มาตามนัด, ยกเลิก, ไม่มา)
- การนำเข้าข้อมูลนัดหมายจากไฟล์ CSV

## 2. ไฟล์หลักในระบบ

### 2.1 app.py - ไฟล์หลักของแอปพลิเคชัน

ไฟล์นี้เป็นไฟล์หลักที่กำหนดเส้นทาง (routes) และจัดการคำขอ HTTP ในแอปพลิเคชัน Flask โดยมีฟังก์ชันสำคัญ:

- `index()` - หน้าแรกแสดงข้อมูลสรุป
- `setup()` - หน้าตั้งค่าการเชื่อมต่อ API
- `subcalendars()` - แสดงรายการปฏิทินย่อย
- `appointments()` - หน้าจัดการนัดหมาย
- `create_appointment()` - API สำหรับสร้างนัดหมายใหม่
- `recurring_appointments()` - หน้าสร้างนัดหมายเกิดซ้ำ
- `update_status()` - หน้าอัปเดตสถานะนัดหมาย
- `import_csv()` - หน้านำเข้าข้อมูลจากไฟล์ CSV

### 2.2 config.py - ไฟล์กำหนดค่าระบบ

ไฟล์นี้จัดการการตั้งค่าของแอปพลิเคชัน โดยโหลดค่าจากไฟล์ .env และกำหนดค่าต่างๆ เช่น:

- `SECRET_KEY` - คีย์ลับสำหรับการเข้ารหัสข้อมูล session
- `DEBUG` - โหมดดีบัก (ควรตั้งเป็น False ในโหมด production)
- `UPLOAD_FOLDER` - โฟลเดอร์สำหรับเก็บไฟล์อัปโหลดชั่วคราว
- `MAX_CONTENT_LENGTH` - ขนาดไฟล์อัปโหลดสูงสุด

### 2.3 teamup_api.py - ไฟล์จัดการการเชื่อมต่อกับ TeamUp API

ไฟล์นี้มีคลาส `TeamupAPI` ที่จัดการการเชื่อมต่อและการทำงานกับ TeamUp Calendar API โดยมีเมธอดสำคัญ:

- `check_access()` - ตรวจสอบการเข้าถึง API
- `get_subcalendars()` - ดึงรายการปฏิทินย่อย
- `get_subcalendar_id()` - รับ ID ของปฏิทินย่อยจากชื่อ
- `get_events()` - ดึงรายการกิจกรรมในช่วงเวลาที่กำหนด
- `create_appointment()` - สร้างนัดหมายเดี่ยว
- `create_recurring_appointment()` - สร้างนัดหมายแบบเกิดซ้ำ
- `update_appointment_status()` - อัปเดตสถานะของนัดหมาย
- `import_from_csv()` - นำเข้าตารางนัดหมายจากไฟล์ CSV

## 3. การติดตั้งระบบบนเซิร์ฟเวอร์

### 3.1 ความต้องการของระบบ

- Python 3.7 หรือสูงกว่า
- pip (ตัวจัดการแพ็คเกจของ Python)
- Web server (แนะนำใช้ Gunicorn + Nginx)
- เครื่องแม่ข่ายที่รันระบบปฏิบัติการ Linux หรือ Windows Server

### 3.2 ขั้นตอนการติดตั้ง

1. **โคลนหรือดาวน์โหลดโค้ด**
   ```bash
   git clone <repository-url>
   cd dialysis_scheduler
   ```

2. **สร้าง Virtual Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # สำหรับ Linux/Mac
   venv\Scripts\activate  # สำหรับ Windows
   ```

### 2. การตั้งค่า Environment Variables

```bash
# คัดลอกไฟล์ตัวอย่าง
cp .env.example .env

# แก้ไขไฟล์ .env
nano .env
```

**ตัวอย่างไฟล์ .env สำหรับ Production:**
```env
# Application Settings
SECRET_KEY=your-super-secret-key-here-change-this
DEBUG=False
ENVIRONMENT=production

# TeamUp API Configuration
TEAMUP_API=tk_1234567890abcdef
CALENDAR_ID=your-calendar-id

# Logging Configuration
LOG_LEVEL=WARNING
LOG_TO_FILE=True
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5

# Security Settings
HIDE_SENSITIVE_DATA=True
SESSION_COOKIE_SECURE=True
SESSION_COOKIE_HTTPONLY=True
```

### 3. การติดตั้งอัตโนมัติ

```bash
# รันสคริปต์ deploy
python scripts/deploy_production.py
```

### 4. การติดตั้งแบบ Manual

```bash
# ติดตั้ง dependencies
pip install -r requirements_production.txt

# สร้างโฟลเดอร์ที่จำเป็น
mkdir -p logs uploads instance

# ตั้งค่า permissions
chmod 600 .env
chmod 755 logs uploads
```

### 5. การทดสอบ

```bash
# ทดสอบการทำงานของ application
python -c "from app import app; print('Application loaded successfully')"

# ทดสอบ API connection
python -c "
from app import teamup_api
if teamup_api:
    success, msg = teamup_api.check_access()
    print(f'API Test: {success} - {msg}')
else:
    print('API not configured')
"
```

## การรัน Production Server

### 1. ใช้ Gunicorn (แนะนำ)

```bash
# รัน production server
gunicorn --bind 0.0.0.0:8000 --workers 4 --timeout 120 app:app

# รันเป็น background process
nohup gunicorn --bind 0.0.0.0:8000 --workers 4 --timeout 120 app:app > gunicorn.log 2>&1 &
```

### 2. ใช้ systemd (Linux)

สร้างไฟล์ `/etc/systemd/system/dialysis-scheduler.service`:

```ini
[Unit]
Description=Dialysis Scheduler Application
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
RuntimeDirectory=dialysis-scheduler
WorkingDirectory=/path/to/dialysis_scheduler
Environment=PATH=/path/to/venv/bin
ExecStart=/path/to/venv/bin/gunicorn --bind 0.0.0.0:8000 --workers 4 app:app
ExecReload=/bin/kill -s HUP $MAINPID
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
# เปิดใช้งาน service
sudo systemctl enable dialysis-scheduler
sudo systemctl start dialysis-scheduler
sudo systemctl status dialysis-scheduler
```

## การจัดการ Logs

### 1. โครงสร้าง Log Files

```
logs/
├── application.log      # Application logs ทั่วไป
├── error.log           # Error logs
└── security.log        # Security-related logs
```

### 2. การตรวจสอบ Logs

```bash
# ดู application logs
tail -f logs/application.log

# ดู error logs
tail -f logs/error.log

# ดู security logs
tail -f logs/security.log

# กรอง logs ตาม level
grep "ERROR" logs/application.log
grep "WARNING" logs/security.log
```

### 3. Log Rotation

Log files จะ rotate อัตโนมัติเมื่อมีขนาดเกิน 10MB และเก็บไว้ 5 ไฟล์

## การ Monitor และ Troubleshooting

### 1. Health Check Endpoints

```bash
# ตรวจสอบสถานะ application
curl http://localhost:8000/

# ตรวจสอบการเชื่อมต่อ API (ถ้า login แล้ว)
curl http://localhost:8000/subcalendars
```

### 2. การแก้ไขปัญหาทั่วไป

**ปัญหา: Cannot connect to TeamUp API**
```bash
# ตรวจสอบ API credentials
grep -E "TEAMUP_API|CALENDAR_ID" .env

# ทดสอบการเชื่อมต่อ
python -c "
import requests
api_key = 'your-api-key'
calendar_id = 'your-calendar-id'
response = requests.get(f'https://api.teamup.com/{calendar_id}/configuration', 
                       headers={'Teamup-Token': api_key})
print(f'Status: {response.status_code}')
"
```

**ปัญหา: High CPU/Memory usage**
```bash
# ตรวจสอบ process
ps aux | grep gunicorn

# ลด workers ถ้าจำเป็น
gunicorn --bind 0.0.0.0:8000 --workers 2 app:app
```

**ปัญหา: Log files เต็ม**
```bash
# บีบอัด logs เก่า
gzip logs/*.log.1 logs/*.log.2

# ลบ logs เก่า (ระวัง!)
find logs/ -name "*.log.*" -mtime +30 -delete
```

### 3. การตรวจสอบ Security

```bash
# ดู security logs
grep "Suspicious\|attack\|WARNING" logs/security.log

# ตรวจสอบ failed login attempts
grep "Unauthorized\|403\|401" logs/application.log
```

## การอัปเดตและบำรุงรักษา

### 1. การอัปเดต Application

```bash
# สำรองข้อมูล
cp -r . ../dialysis_scheduler_backup_$(date +%Y%m%d)

# อัปเดตโค้ด
git pull origin main

# อัปเดต dependencies
pip install -r requirements_production.txt

# รีสตาร์ท service
sudo systemctl restart dialysis-scheduler
```

### 2. การสำรองข้อมูล

```bash
# สำรองไฟล์ configuration
tar -czf backup_config_$(date +%Y%m%d).tar.gz .env uploads/ logs/

# สำรองทั้งระบบ
tar -czf backup_full_$(date +%Y%m%d).tar.gz --exclude=venv --exclude=__pycache__ .
```

### 3. การทำความสะอาดระบบ

```bash
# ลบ cache files
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} +

# ลบ temporary files
rm -rf uploads/temp*
```

## การตั้งค่า Reverse Proxy (Nginx)

### 1. ติดตั้ง Nginx

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install nginx

# CentOS/RHEL
sudo yum install nginx
```

### 2. กำหนดค่า Nginx

สร้างไฟล์ `/etc/nginx/sites-available/dialysis-scheduler`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Referrer-Policy strict-origin-when-cross-origin;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/m;

    location / {
        limit_req zone=api burst=20 nodelay;
        
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Static files (ถ้ามี)
    location /static {
        alias /path/to/dialysis_scheduler/static;
        expires 1d;
    }

    # Access logs
    access_log /var/log/nginx/dialysis-scheduler.access.log;
    error_log /var/log/nginx/dialysis-scheduler.error.log;
}
```

```bash
# เปิดใช้งาน site
sudo ln -s /etc/nginx/sites-available/dialysis-scheduler /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## การตั้งค่า SSL/HTTPS

### 1. ใช้ Let's Encrypt

```bash
# ติดตั้ง Certbot
sudo apt install certbot python3-certbot-nginx

# สร้าง SSL certificate
sudo certbot --nginx -d your-domain.com

# ทดสอบ auto-renewal
sudo certbot renew --dry-run
```

### 2. การ Redirect HTTP to HTTPS

แก้ไขไฟล์ Nginx configuration:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # SSL Security settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
    ssl_prefer_server_ciphers off;

    # ... rest of configuration
}
```

## การ Monitor ด้วย External Tools

### 1. การตั้งค่า Monitoring

```bash
# สร้าง monitoring script
cat > scripts/health_check.sh << 'EOF'
#!/bin/bash
URL="http://localhost:8000"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" $URL)

if [ $STATUS -eq 200 ]; then
    echo "OK - Application is running"
    exit 0
else
    echo "CRITICAL - Application returned HTTP $STATUS"
    exit 2
fi
EOF

chmod +x scripts/health_check.sh
```

### 2. การตั้งค่า Alerting

```bash
# สร้าง cron job สำหรับ monitoring
echo "*/5 * * * * /path/to/scripts/health_check.sh || echo 'Alert: Dialysis Scheduler is down' | mail -s 'Server Alert' admin@example.com" | crontab -
```

## Best Practices สำหรับ Production

### 1. Security Checklist

- [ ] เปลี่ยน SECRET_KEY ใน .env
- [ ] ตั้งค่า HTTPS
- [ ] ใช้ strong passwords
- [ ] ตั้งค่า firewall
- [ ] อัปเดต OS และ dependencies เป็นประจำ
- [ ] ตรวจสอบ logs เป็นประจำ

### 2. Performance Optimization

- [ ] ตั้งค่า caching (Redis/Memcached)
- [ ] ใช้ CDN สำหรับ static files
- [ ] Optimize database queries
- [ ] Monitor และ tune Gunicorn workers

### 3. Backup Strategy

- [ ] สำรองข้อมูลทุกวัน
- [ ] ทดสอบการ restore
- [ ] เก็บ backup ในสถานที่ปลอดภัย
- [ ] มี disaster recovery plan

## การแก้ไขปัญหาเฉพาะกิจ

### Error: "API Token Invalid"
```bash
# ตรวจสอบและแก้ไข API token
grep TEAMUP_API .env
# ตรวจสอบจาก TeamUp dashboard และอัปเดตในไฟล์ .env
```

### Error: "Database Lock"
```bash
# ถ้าใช้ SQLite (ในอนาคต)
fuser uploads/database.db
kill -9 <PID>
```

### High Memory Usage
```bash
# ลด Gunicorn workers
pkill -f gunicorn
gunicorn --bind 0.0.0.0:8000 --workers 2 --max-requests 1000 app:app
```

---

## สรุป

การใช้งานระบบ Dialysis Scheduler ใน production ต้องมีการเตรียมการดังนี้:

1. **การติดตั้งที่ปลอดภัย** - ใช้ HTTPS, strong passwords, และ proper file permissions
2. **การ Monitor ที่เหมาะสม** - ตั้งค่า logging, alerting, และ health checks
3. **การบำรุงรักษา** - สำรองข้อมูล, อัปเดต, และการทำความสะอาดระบบ
4. **การแก้ไขปัญหา** - มี process สำหรับการ troubleshoot และ disaster recovery

การปฏิบัติตาม best practices เหล่านี้จะช่วยให้ระบบทำงานได้อย่างเสถียรและปลอดภัยใน production environment