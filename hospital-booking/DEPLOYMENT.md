# แผนการ Deploy ระบบ NudDee (Hospital Booking) ขึ้น Production

> อัปเดตล่าสุด: มิถุนายน 2026
> สถานะ: แผน — ยังไม่ได้ deploy จริง

## 1. ภาพรวมสถาปัตยกรรมบน Production

```
                         ┌─────────────────────────────┐
   *.nuddee.com  ──────► │  Nginx (443, SSL wildcard)  │
                         └──────────┬──────────────────┘
                  /api/* ──────────►│◄────────── อื่นๆ ทั้งหมด
                         ┌──────────┴──────────┐
              ┌──────────▼─────────┐ ┌─────────▼──────────┐
              │ FastAPI (uvicorn)  │ │ Flask (gunicorn)   │
              │ 127.0.0.1:8000     │ │ 127.0.0.1:5001     │
              └──────────┬─────────┘ └─────────┬──────────┘
                         │      ┌──────────────┤
              ┌──────────▼──────▼───┐ ┌────────▼───────────┐
              │ PostgreSQL          │ │ Redis              │
              │ (public + tenant_*) │ │ (RQ + Celery)      │
              └─────────────────────┘ └────────┬───────────┘
                                  ┌────────────┼────────────┐
                          ┌───────▼──────┐ ┌───▼──────┐ ┌───▼─────────┐
                          │ RQ worker    │ │ Celery   │ │ Celery beat │
                          │ (SMS/email)  │ │ worker   │ │ (holidays)  │
                          └──────────────┘ └──────────┘ └─────────────┘

   Super Admin panel (run_admin.py, port 5002) — bind เฉพาะ 127.0.0.1
   เข้าผ่าน SSH tunnel หรือ VPN เท่านั้น ไม่เปิดสู่อินเทอร์เน็ต
```

Process ที่ต้องรันทั้งหมด 6 ตัว: FastAPI, Flask, Admin, RQ worker, Celery worker, Celery beat
(แนะนำจัดการด้วย systemd — ดูข้อ 5)

## 2. สิ่งที่ต้องเตรียม (Infrastructure)

| รายการ | สเปกขั้นต่ำ | หมายเหตุ |
|---|---|---|
| Server | 2 vCPU / 4 GB RAM, Ubuntu 22.04+ | VPS เดียวพอสำหรับช่วงแรก |
| PostgreSQL | 14+ | ใช้ managed DB ได้ (แนะนำ — ได้ backup อัตโนมัติ) |
| Redis | 6+ | รันบนเครื่องเดียวกันได้ |
| Domain | `nuddee.com` + **wildcard DNS** `*.nuddee.com` → server | จำเป็นเพราะ multi-tenant ใช้ subdomain |
| SSL | **Wildcard certificate** `*.nuddee.com` | Let's Encrypt ต้องใช้ DNS-01 challenge (certbot + plugin ของผู้ให้บริการ DNS) |
| SMTP | Gmail app password ใช้ชั่วคราวได้ แต่ production ควรใช้ SendGrid/Mailgun/SES | Gmail มี rate limit ~500 ฉบับ/วัน |
| SMS | บัญชี NT Digital ที่ active | มี credential อยู่แล้วใน .env |
| Stripe | Production keys + webhook endpoint | ดูข้อ 7 |

## 3. ⚠️ เรื่อง Security ที่ต้องทำ "ก่อน" deploy

1. **Rotate Stripe live keys** — `.env` ปัจจุบันมี `sk_live_...` (live key จริง) วางอยู่บนเครื่อง dev
   ควร revoke แล้วออกใหม่ และเก็บ production secrets แยกจากเครื่อง dev เสมอ
2. **Rotate Gmail app password และ NT SMS password** ด้วยเหตุผลเดียวกัน
3. **ตั้ง `SECRET_KEY` ใหม่** — โค้ดมี fallback เป็น `"a-dev-secret-key"` ถ้าไม่ตั้งค่า
   (`flask_app/app/__init__.py`) สร้างด้วย `python -c "import secrets; print(secrets.token_hex(32))"`
4. **ปิด debug mode** — `flask_app/run.py` ฮาร์ดโค้ด `debug=True` → production ต้องรันผ่าน gunicorn แทน `python run.py`
5. **Session cookie** — ตั้ง `SESSION_COOKIE_SECURE=True` เมื่อใช้ HTTPS
6. **Admin panel** — bind `ADMIN_HOST=127.0.0.1` (ค่า default ถูกแล้ว) อย่าเปิด port 5002 ใน firewall
7. **มี `.gitignore` แล้ว** (เพิ่มในคอมมิตนี้) — ตรวจว่า `.env` ไม่เคยถูก commit: `git log --all -- .env`

## 4. Environment Variables สำหรับ Production

สร้าง `/etc/nuddee/.env` (อย่าใช้ไฟล์เดียวกับ dev):

```bash
ENVIRONMENT=production
DOMAIN=nuddee.com                 # โดเมนจริง
USE_HTTPS=true

DATABASE_URL=postgresql://nuddee:<password>@<db-host>:5432/nuddee
REDIS_URL=redis://localhost:6379/0
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=1

SECRET_KEY=<token ใหม่ 64 ตัวอักษร>
FASTAPI_BASE_URL=http://127.0.0.1:8000   # internal call ไม่ต้องออก internet

STRIPE_SECRET_KEY=sk_live_<ใหม่>
STRIPE_PUBLISHABLE_KEY=pk_live_<ใหม่>
STRIPE_WEBHOOK_SECRET=whsec_<จาก endpoint production>

MAIL_SERVER=smtp.sendgrid.net
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=apikey
MAIL_PASSWORD=<sendgrid key>
MAIL_DEFAULT_SENDER=noreply@nuddee.com
EMAIL_SENDER=noreply@nuddee.com

NT_SMS_HOST=smsgw.mybynt.com
NT_SMS_API=/service/SMSWebServiceEngine.php
NT_SMS_USER=<ใหม่>
NT_SMS_PASS=<ใหม่>
NT_SMS_SENDER=NTDigital
# ส่ง SMS แจ้งเลื่อน/ยกเลิกนัดเมื่อผู้จองไม่มีอีเมล (default ปิด — ระบบจะเตือนให้เจ้าหน้าที่โทรแทน)
ENABLE_SMS_NOTIFICATIONS=false

ADMIN_HOST=127.0.0.1
ADMIN_PORT=5002
LOG_LEVEL=INFO
```

## 5. ขั้นตอน Deploy (ครั้งแรก)

### 5.1 เตรียมเครื่อง

```bash
sudo apt update && sudo apt install -y python3.10 python3.10-venv nginx redis-server postgresql-client certbot
sudo useradd -m -s /bin/bash nuddee
sudo -u nuddee git clone <repo> /home/nuddee/hospital-booking
cd /home/nuddee/hospital-booking
sudo -u nuddee python3.10 -m venv venv
sudo -u nuddee venv/bin/pip install -r requirements.txt
```

### 5.2 Database

```bash
createdb -h <db-host> -U postgres nuddee
# ตาราง public schema ถูกสร้างอัตโนมัติตอน app start ครั้งแรก (PublicBase.metadata.create_all)
# จากนั้นรัน migrations ตามลำดับ:
cd migrations
python add_tenant_management.py
python add_availability_templates.py
python add_provider_availability_structures.py
python add_holiday_features.py
# สร้าง super admin คนแรก:
python ../scripts/create_super_admin.py
```

> หมายเหตุ: โปรเจกต์ยังไม่ใช้ Alembic — migration เป็น script รันมือ ลำดับสำคัญ
> ระยะยาวควรย้ายไป Alembic เพื่อให้ track ได้ว่า migration ไหนรันแล้ว

### 5.3 systemd units (6 services)

ตัวอย่าง `/etc/systemd/system/nuddee-flask.service`:

```ini
[Unit]
Description=NudDee Flask app
After=network.target postgresql.service redis-server.service

[Service]
User=nuddee
WorkingDirectory=/home/nuddee/hospital-booking/flask_app
EnvironmentFile=/etc/nuddee/.env
ExecStart=/home/nuddee/hospital-booking/venv/bin/gunicorn -w 4 -b 127.0.0.1:5001 "app:create_app()"
Restart=always

[Install]
WantedBy=multi-user.target
```

สร้างแบบเดียวกันอีก 5 ไฟล์ โดยเปลี่ยนเฉพาะ `WorkingDirectory`/`ExecStart`:

| Unit | ExecStart |
|---|---|
| `nuddee-fastapi` | `venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2` (WorkingDirectory=`.../fastapi_app`) |
| `nuddee-admin` | `venv/bin/python run_admin.py` (WorkingDirectory=root) |
| `nuddee-rq` | `venv/bin/python worker.py` (WorkingDirectory=root) |
| `nuddee-celery` | `venv/bin/celery -A flask_app.celery_worker worker --loglevel=info` (WorkingDirectory=root) |
| `nuddee-beat` | `venv/bin/celery -A flask_app.celery_worker beat --loglevel=info` (WorkingDirectory=root) |

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nuddee-fastapi nuddee-flask nuddee-admin nuddee-rq nuddee-celery nuddee-beat
```

> เช็คก่อนว่า `gunicorn "app:create_app()"` เรียก app factory ได้ — ถ้า `create_app()` ของ
> โปรเจกต์รับ argument หรือชื่อไม่ตรง ให้สร้างไฟล์ `wsgi.py` ที่ instantiate app แล้วชี้ gunicorn ไปที่นั่นแทน

### 5.4 Nginx + SSL

มี config ตั้งต้นอยู่แล้วที่ [nginx/nginx.conf](nginx/nginx.conf) — แก้ `yourdomain.com` เป็นโดเมนจริง แล้วเพิ่ม SSL:

```bash
# ขอ wildcard cert (DNS-01 — ต้องใช้ plugin ตามผู้ให้บริการ DNS เช่น cloudflare)
sudo certbot certonly --dns-cloudflare -d "nuddee.com" -d "*.nuddee.com"
```

จุดสำคัญใน nginx config:
- `server_name nuddee.com *.nuddee.com;`
- `location /api/ { proxy_pass http://127.0.0.1:8000; }`
- `location / { proxy_pass http://127.0.0.1:5001; }` พร้อมส่ง `Host` header เดิม (Flask ใช้แยก subdomain)
- redirect HTTP → HTTPS
- **อย่า** proxy port 5002 (admin) ออก internet

### 5.5 Stripe webhook

1. ใน Stripe Dashboard → Developers → Webhooks → Add endpoint: `https://nuddee.com/api/webhook`
2. เลือก event `checkout.session.completed` (ตามที่ handler ใน `fastapi_app/app/main.py` รองรับ)
3. เอา signing secret มาใส่ `STRIPE_WEBHOOK_SECRET`
4. ⚠️ Price IDs ถูกฮาร์ดโค้ดใน `fastapi_app/app/main.py` — ตรวจว่าตรงกับ product จริงใน Stripe account

### 5.6 ตรวจรับระบบ (smoke test)

```bash
curl -I https://nuddee.com                      # Flask landing
curl https://nuddee.com/api/docs                # FastAPI docs (พิจารณาปิดใน production)
# ทดสอบสมัครโรงพยาบาลใหม่ → เช็คว่า tenant schema + ข้อมูลเริ่มต้นถูกสร้าง
# ทดสอบจองคิวจากหน้า public booking ของ tenant ทดสอบ จนจบ flow
sudo -u nuddee redis-cli ping
sudo systemctl status nuddee-*
```

## 6. งานหลัง deploy (operations)

- **Backup**: `pg_dump` รายวัน (ต้อง dump ทุก schema — ใช้ `pg_dump -Fc nuddee` ทั้ง database) + เก็บ offsite
- **Log rotation**: ใช้ journald อยู่แล้วถ้ารันผ่าน systemd; ตั้ง `SystemMaxUse=1G`
- **Monitoring ขั้นต่ำ**: uptime check ที่ `https://nuddee.com` + ตรวจ `systemctl is-failed nuddee-*` ผ่าน cron แจ้งเตือน
- **อัปเดตโค้ด**: `git pull` → `pip install -r requirements.txt` → รัน migration ใหม่ (ถ้ามี) → `sudo systemctl restart nuddee-*`

## 7. สิ่งที่ "ควรแก้ในโค้ด" ก่อนเปิดให้บริการจริง

เรียงตามความสำคัญ (รายละเอียดเต็มดูรายงานการสำรวจ):

1. ~~**Email ยืนยันการจองยังเป็น mock**~~ — ✅ **แก้แล้ว (มิ.ย. 2026)**: อีเมลยืนยัน/เลื่อน/ยกเลิกนัด
   ส่งจริงผ่าน SMTP แล้ว (`fastapi_app/app/email_service.py`) — production ต้องตั้ง `MAIL_*` ให้ครบ
2. ~~**ลืมรหัสผ่าน / password reset ยังไม่มี**~~ — ✅ **แก้แล้ว (มิ.ย. 2026)**: /auth/forgot-password
   ด้วย OTP ทางอีเมล อายุ 15 นาที มี rate limit
3. ~~**หน้า Terms of Service / Privacy Policy เป็นลิงก์ตาย**~~ — ✅ **แก้แล้ว (มิ.ย. 2026)**:
   มีหน้า /terms + /privacy แล้ว ⚠️ เนื้อหาเป็นแม่แบบ — **ให้ที่ปรึกษากฎหมายตรวจก่อนเปิดบริการจริง**
   และแก้ชื่อบริษัท/อีเมลติดต่อใน `flask_app/app/templates/legal/` ให้เป็นข้อมูลจริง
4. ~~**การแจ้งเตือนเลื่อน/ยกเลิกนัดฝั่ง Flask admin ยังเป็น TODO**~~ — ✅ **แก้แล้ว (มิ.ย. 2026)**:
   admin เลื่อน/ยกเลิก/ขอเลื่อนนัด → ผู้รับบริการได้อีเมลอัตโนมัติ; ถ้าไม่มีอีเมลแต่มีเบอร์
   ระบบเตือนเจ้าหน้าที่ให้โทรแจ้ง (แสดงเบอร์); SMS เป็น option เปิดด้วย `ENABLE_SMS_NOTIFICATIONS=true`
5. **Role-based access control ยังไม่บังคับใช้** — มี enum role แต่ route ไม่เช็คสิทธิ์
6. **ยังไม่มี test เลย** — อย่างน้อยควรมี test ครอบ flow การจอง + การสร้าง tenant ก่อนเปิดจริง
7. ~~**ลบตาราง tenant ที่หลงอยู่ใน public schema**~~ — ✅ **ลบแล้ว 13 ตาราง (มิ.ย. 2026)**
   เหลือ `public.holidays` (มีข้อมูล 19 แถว backup ไว้ที่ migrations/backups/ แล้ว) —
   ลบให้ครบด้วย `python migrations/drop_stray_public_tenant_tables.py --execute --force`
