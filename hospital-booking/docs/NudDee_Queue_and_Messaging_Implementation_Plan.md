# NudDee SaaS — แผน Implementation: ระบบคิว, Check-in, และการเชื่อมต่อ LINE/Telegram/PWA

> **เอกสารนี้คืออะไร:** แผนงานฉบับสมบูรณ์สำหรับให้ Claude Code / Claude Cowork ทำงานต่อได้โดยไม่ต้องเดา context
> **ขอบเขต:** ระบบจองช่วงเวลา + จับคิวหน้างาน (slot-type 2), priority queue, grace rule, การประมาณเวลารอ, และการเชื่อมต่อ LINE/Telegram/PWA แบบคุมต้นทุน
> **อ่านส่วนที่ 0 และ 1 ให้จบก่อนเริ่มเขียน code เสมอ** — มีกฎที่ถ้าพลาดจะเกิด regression ซ้ำที่เคยเจอมาแล้ว

---

## 0. CRITICAL RULES — อ่านก่อนทำทุกครั้ง (ห้ามข้าม)

กฎเหล่านี้สำคัญกว่าความสะดวก ถ้าฝ่าฝืนจะเกิดบั๊กที่เคยเจอซ้ำ ๆ มาแล้ว

### 0.1 Flask-first principle (สำคัญที่สุด)
- **Business logic ทั้งหมดอยู่ที่ Python** (Flask + FastAPI) และ render ผ่าน Jinja2 server-side
- **FastAPI = data/API backend เท่านั้น** ไม่ใส่ business logic ที่ตัดสินใจลงไป
- **ห้ามผลัก logic ไป JavaScript/AJAX** เว้นแต่ถูกสั่งชัดเจน
- JS ใช้ได้เฉพาะ: (ก) SDK glue ที่ platform บังคับ (LIFF SDK, Telegram WebApp), (ข) display ล้วน ๆ เช่น auto-refresh จอคิว, กราฟ Chart.js — ไม่ใช่การตัดสินใจ

### 0.2 FastAPI tenant schema pattern (เคย regression ซ้ำ — ห้ามลืม)
**กฎใหม่ (แก้ 13 มิ.ย. 2026): ผูก session ด้วย `bind_tenant()` เสมอ — ไม่ใช่แค่ `SET search_path` manual**

ที่มา: `shared_db.database` มี event `after_begin` ที่ SET search_path ให้ "ทุก transaction" ของ session:
- session ที่ผูก tenant (`bind_tenant`) → SET tenant ทุก transaction
- session ที่ "ไม่ผูก" → **SET `public` ทุก transaction** (กัน connection ค้าง tenant path ปนเปื้อนข้าม tenant)

ผลคือ ถ้าใช้แค่ `SET search_path` manual โดยไม่ `bind_tenant` แล้ว `commit()/rollback()` ก่อน query/refresh
ต่อ → transaction ใหม่จะถูกบังคับ `public` → `UndefinedTable` (เพราะ session ยัง "ไม่ผูก") **pattern ที่ถูก:**
```python
from shared_db.database import bind_tenant
# แก้ 13 มิ.ย. 2026 (B1): **ห้าม reconstruct `f"tenant_{subdomain}"`** — subdomain มี hyphen ได้
# (`my-clinic` → schema `tenant_myclinic` ไม่ใช่ `tenant_my-clinic`) ต้อง resolve เสมอ:
schema_name = resolve_schema(db, subdomain)  # FastAPI: fastapi_app/app/tenant.py (query public.hospitals.schema_name)
                                             # Flask: TenantManager.resolve_schema (middleware ผูก g.db ให้แล้ว)
bind_tenant(db, schema_name)                 # ผูก -> after_begin คุม search_path ทุก transaction (รวมหลัง commit)
db.execute(text(f'SET search_path TO "{schema_name}", public'))  # SET ซ้ำเฉพาะ transaction "ปัจจุบัน" ที่เปิดไปแล้ว
# ... query / เขียนข้อมูล ...
db.commit()                                  # write: commit ที่ "ท้าย" งาน (ไม่ใช่หลัง SET); query/refresh หลัง commit ทำได้เพราะ bound
```
- **ห้าม commit ทันทีหลัง SET** (ของเดิมยังจริง) — commit ที่ท้ายงานเท่านั้นถ้าเป็น write
- **ต้อง `bind_tenant`** ไม่งั้น commit แล้ว query/refresh ต่อจะพัง (legacy FastAPI ทุก module migrate มาใช้ helper ที่ bind แล้ว: `availability.get_tenant_db`, `event_types.get_tenant_session`, `booking/holidays._set_tenant`)
- ใช้ `Depends(get_db)` + `bind_tenant` (Flask middleware ผูก g.db ให้อัตโนมัติ) — **ห้ามใช้** `Depends(get_tenant_db)` แบบ factory เดิม (จะเกิด `AttributeError: 'function' object has no attribute 'execute'`)
- `schema_name` "มักจะ" อยู่ในรูป `tenant_<subdomain>` (เช่น `tenant_humnoi`) **แต่ไม่เสมอ** — registration sanitize ชื่อ (ตัด hyphen) → ห้ามอนุมานจาก subdomain ตรง ๆ ต้องอ่านจาก `public.hospitals.schema_name` (ดู B1 ด้านบน + กฎ §9.3)

### 0.3 Subdomain detection
- pattern `*.localhost` (เช่น `humnoi.localhost`) **ต้องถูกรับรองเป็น subdomain ที่ถูกต้อง** ใน `tenant_manager.py`
- URL generation ใช้ `flask_app/app/utils/url_helper.py` (context-aware) — อย่า hardcode `?subdomain=` query param

### 0.4 มาตรฐานอื่น
- **Date format:** `dd/mm/yyyy` (วัน/เดือน/ปี ตามแบบไทย) ใช้ Jinja2 filter `thai_date` ที่อยู่ใน `flask_app/app/__init__.py`
- **Timezone (G) (สำคัญ — กัน grace เลื่อน 7 ชม.):** `sessions.start_time/end_time` เป็น `TIME` (ไม่มี tz) — เวลาประกอบ `session_date + start_time/end_time` เพื่อเทียบกับ `now` ต้อง **materialize/compare ใน timezone ของ tenant เสมอ (default `Asia/Bangkok`)** ห้ามตีความ `TIME` เป็น UTC; `now` ที่ส่งเข้า service ต้องเป็น tz-aware โซนเดียวกัน (ดู §5.3, §5.8)
- **Identity / `patient_ref` (A) (บังคับ):** ใช้รูป canonical เดียวทั้งระบบ — ดู §4.6.1 (ห้ามใช้ชื่อเป็น key; ยังไม่ link identity → notification เป็น pull/log เท่านั้น)
- **Token/secret ทุกตัวต้องเข้ารหัสตอนเก็บ (encrypt at rest)** — ห้ามเก็บ LINE channel secret / access token / Telegram bot token เป็น plaintext ใน DB
- **ภาษา:** UI/ข้อความถึงผู้ใช้เป็นภาษาไทย, code/identifier เป็นภาษาอังกฤษ
- การ debug codebase: ใช้ `search_files` กับ pattern ชื่อฟังก์ชัน (เช่น `def edit_template`) แทนการอ่านทั้งไฟล์

### 0.5 ต้นทุน LINE — กฎที่กำหนดสถาปัตยกรรมการแจ้งเตือน (อ่านส่วนที่ 6 ประกอบ)
- **เสียเงิน:** push / multicast / broadcast / narrowcast — นับตาม **จำนวนผู้รับ** (push หา 5 คน = 5 ข้อความ)
- **ฟรี (synchronous เท่านั้น):** reply message (ต้องมี reply token จาก webhook, ใช้ครั้งเดียว, หมดอายุเร็ว), `liff.sendMessages()` (client-side, ส่งในนามผู้ใช้)
- **ฟรี (asynchronous):** Telegram bot message, PWA Web Push, pull-based (ผู้ใช้เปิดแอปดูเอง)
- **ข้อจำกัดที่ต้องเข้าใจ:** reply message และ liff.sendMessages **ใช้ส่งแจ้งเตือนแบบตั้งเวลา/async ไม่ได้** เพราะ reply token มีเฉพาะใน webhook context และ liff.sendMessages เป็น client-side ดังนั้น **การแจ้งเตือนแบบ async ผ่าน LINE มีทางเดียวคือ push (เสียเงิน)** — อย่าพยายามเรียก "free LINE reply" จาก cron/background job (เป็นไปไม่ได้)

---

## 1. Context ของโปรเจกต์ (สำหรับ agent ที่ไม่มี memory เดิม)

### 1.1 ภาพรวม
- **ชื่อ:** NudDee SaaS / nandt hospital-booking
- **ที่ตั้ง:** `/Users/seal/Documents/GitHub/nandt/hospital-booking/`
- **ประเภท:** Multi-tenant SaaS สำหรับจัดการนัดหมายของโรงพยาบาล
- **Multi-tenancy:** subdomain-based routing (เช่น `humnoi.localhost`) + PostgreSQL per-tenant schema (เช่น `tenant_humnoi`)
- **Database:** PostgreSQL ชื่อ `nuddee`

### 1.2 Stack
| ส่วน | เทคโนโลยี |
|---|---|
| Web/UI + business logic | Flask (port 5001) + Jinja2 + WTForms + Bootstrap 5 |
| Data/API backend | FastAPI |
| Database | PostgreSQL (multi-schema multi-tenant) |
| ORM | SQLAlchemy |
| Calendar integration | TeamUp calendar API |
| File operations (dev) | custom `teamup-project` MCP tool |

### 1.3 Key file paths (ของจริงในโปรเจกต์)
```
flask_app/app/availability_routes.py     # Flask routes (availability)
flask_app/app/auth.py                     # auth
flask_app/app/routes.py                   # routes หลัก
flask_app/app/models.py                   # SQLAlchemy models
flask_app/app/forms.py                    # WTForms
flask_app/app/__init__.py                 # app init + Jinja2 filters (thai_date ฯลฯ)
flask_app/app/utils/url_helper.py         # context-aware URL generation
flask_app/app/templates/settings/availability/index.html
flask_app/app/templates/settings/availability/form.html
fastapi_app/app/availability.py           # FastAPI availability endpoints
```
> หมายเหตุ: ไฟล์/route ใหม่ที่เอกสารนี้กำหนด ให้สร้างเพิ่มในโครงเดียวกัน (เช่น `queue_routes.py`, `webhook_routes.py`, `fastapi_app/app/queue.py`)

### 1.4 สถานะปัจจุบัน (Current State)
- **Public booking** (`/book/subdomain=humnoi`) ใช้งานได้แล้ว มี anti-spam: honeypot, time-based token, session-based booking limit, DB-level duplicate prevention (กันคนเดิม + event type เดิม + วันเดียวกัน + ตรวจ time-overlap ข้าม event type)
- **Availability/settings** (`/settings/availability`) ใช้งานได้บางส่วน
  - decisions ที่ final แล้ว: date override ที่สร้างใหม่เป็น template-specific (ผูก `template_id` กับ `availability_templates`); legacy global override ยังอ่านเป็น fallback ได้เพื่อ backward compatibility; เอา `provider_id` ออกจากทั้ง `availabilities` และ `date_overrides`, migration รันบน schema `tenant_humnoi`
- **Subdomain URL routing** แก้แล้ว: `http://humnoi.localhost/dashboard` ไม่ append `?subdomain=` ผิด ๆ อีก (จัดการโดย `url_helper.py`)
- **Queue/priority/grace/session/estimation/notify base/analytics base** implement แล้ว (14–15 มิ.ย. 2026) และ pytest ล่าสุดผ่าน `94 passed`
- **A1 `event_types.requires_queue`** implement แล้ว: migration + SQLAlchemy model + FastAPI create/update/response + settings UI + check-in arrival-only path + tests

### 1.5 Known Issues / pre-existing (นอกขอบเขตแผนนี้ แต่ต้องรู้)
- **ปุ่ม save บนหน้า template edit** (`/settings/availability/template/{id}/edit`) **ยังไม่ทำงาน** ณ สิ้นสุด session ล่าสุด → ถ้างานในแผนนี้ต้องพึ่งหน้านั้น ให้แจ้งและแก้ก่อน แต่ไม่ใช่เป้าหมายหลักของแผนนี้

---

## 2. Architectural Decisions ที่ล็อกแล้ว (อย่า re-litigate)

decisions เหล่านี้ตัดสินใจร่วมกับเจ้าของโปรเจกต์แล้ว ให้ทำตามโดยไม่ต้องเสนอทางเลือกใหม่

1. **LINE OA + Telegram bot แยกต่อ tenant** — แต่ละโรงพยาบาลมี LINE Official Account และ Telegram bot ของตัวเอง (brand เดียวกัน), เก็บ credential/token ต่อ schema, tenant จ่าย LINE เอง (Telegram ฟรี) — Telegram bot รองรับ **2 รูปแบบเจ้าของ: SaaS จัดการ หรือ tenant สร้างเอง (BYO token)** runtime เหมือนกัน (ดู §6.8); ทางเลือก shared Telegram bot ดู §6.4
2. **LINE/Telegram = ทางผ่านเข้าแอป ไม่ใช่ท่อ push** — ดันทุก event ไปช่องฟรีให้มากสุด; LINE เหลือ push เสียเงินเฉพาะ "ใกล้/ถึงคิว", **Telegram push ฟรีเสมอ** (ไม่มีค่าต่อข้อความ)
3. **Mini App = web app เดิม + SDK glue** — ไม่เขียน SPA ใหม่ หน้า Jinja2 เดิมเป็น LIFF/Telegram Mini App ได้ทันที
4. **คิว: การจอง = ตั๋วคิว, check-in = ตัวกำหนดลำดับ** — ไม่ซื้อระบบคิว/ตู้กดบัตร, จอคิวคือหน้า Jinja2 บน TV
5. **Appointment vs walk-in: สลับแบบให้ priority คนนัดมากกว่า** — เริ่มด้วย ratio interleaving (โปร่งใส) แล้วอัปเกรดเป็น score model ได้
6. **Grace rule: มีน้ำใจแต่เป็นธรรม** — อยู่ช่วงผ่อนผัน → priority เต็ม; วันเดียวกันแต่นอกช่วง → demote เป็น walk-in; ไม่มาจนปิด → no_show
7. **Wait estimation: ทำ level 1-2 ก่อน** (avg service time × คนข้างหน้า / servers, ใช้ p50/p80) แต่วาง seam ให้สลับเป็น level 3/4 ได้
8. **ทุกอย่างขับด้วย config ต่อ tenant** — policy เป็นข้อมูลใน DB ไม่ใช่ hardcode
9. **Channel parity (LINE = Telegram):** ทุก surface ต้องทำได้ทั้งสองช่อง — chat entry, mini app, QR check-in, การยืนยัน, การแจ้งเตือน; ใช้หน้า web เดียวกัน detect context แล้วโหลด SDK ที่ถูก (ดู 6.0 + 6.7)
10. **Session ใช้ time slot เดิมที่ตั้งไว้ในระบบ (ไม่ตั้งซ้ำ)** — `sessions` คือการ materialize availability/time slot ที่มีอยู่แล้วให้เป็นแถวจริงต่อวันต่อ service_point; ใช้กับ `slot_type='window'` เป็นหลัก ส่วน `slot_type='exact'` ใช้เวลานัดตรงได้โดย session เป็น optional (ดู 5.8)

---

## 3. ภาพรวมสถาปัตยกรรมที่จะสร้าง

### 3.1 Surfaces 3 ชั้น (web app เดียว)
```
ชั้น 1  Chat bot         → ทางเข้า + แจ้งเตือน (webhook = Flask/FastAPI route)
ชั้น 2  Mini App         → หน้า Jinja2 เดิม + SDK glue (LIFF / Telegram WebApp)
ชั้น 3  PWA              → web app เดิม + manifest + service worker + Web Push
```

### 3.2 Flow หลัก (state machine ของ queue entry)
```
booked ──check-in──> checked_in ──call next──> called ──> in_service ──> done
   │                     │                        │
   │(ไม่มาจนปิด)          │(grace: demote)         │(ไม่มาเรียกแล้ว)
   ▼                     ▼                        ▼
no_show              [reclass เป็น walkin]      skipped
```

> **หมายเหตุ (re-queue หลัง skipped):** ตอนนี้ `skipped` เป็น terminal แต่จริง ๆ คนที่ถูกข้ามมักกลับมาเรียกใหม่ได้ — เพิ่ม action ให้ staff ดึง skipped กลับเข้า active (insert event ใหม่) เป็น **Phase หลัง channel (หลัง Phase 4)** ไม่ใช่ blocker ตอนนี้

### 3.3 Data flow ของการประมาณเวลา + analytics
```
ทุก state transition → เขียนลง queue_events (append-only)
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
   real-time display   estimate_wait()   analytics dashboard (ทีหลัง)
                       (level 1-2 now)
```

---

## 4. Database Schema (DDL)

> **วิธีรัน migration:** เปิด psql เชื่อม DB `nuddee` แล้ว `SET search_path TO tenant_humnoi;` ก่อนรัน DDL ทุกครั้ง (ทำซ้ำต่อ tenant schema ที่ต้องการ)
> ตารางทั้งหมดสร้างใน **tenant schema** เว้นแต่ระบุว่าเป็น control/shared
> ตรวจ existing columns ก่อน ALTER เสมอ (`\d appointments`)

### 4.1 `service_points` — จุดบริการ (ห้อง/เคาน์เตอร์/หมอ)
```sql
CREATE TABLE IF NOT EXISTS service_points (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,
    sp_type         VARCHAR(20) NOT NULL DEFAULT 'room',   -- room | counter | doctor
    parallel_servers SMALLINT NOT NULL DEFAULT 1,          -- จำนวนช่องบริการขนานกัน
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 4.2 `sessions` — ช่วงเวลาบริการต่อจุดบริการต่อวัน
```sql
CREATE TABLE IF NOT EXISTS sessions (
    id              SERIAL PRIMARY KEY,
    service_point_id INTEGER NOT NULL REFERENCES service_points(id),
    session_date    DATE NOT NULL,
    name            VARCHAR(100) NOT NULL,                 -- 'เช้า' | 'บ่าย' | ฯลฯ
    start_time      TIME NOT NULL,
    end_time        TIME NOT NULL,
    capacity        INTEGER,                               -- nullable = ไม่จำกัด
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (service_point_id, session_date, name)
);
```
> **TODO integration:** sessions สามารถ generate จาก availability template เดิมได้ (ผูกกับ TeamUp/`availabilities`) — Phase 1 ทำ manual seed ก่อน, Phase ถัดไปค่อยทำ generator

### 4.3 ส่วนขยาย `appointments` (ALTER — ตรวจก่อนว่ายังไม่มี column)
```sql
ALTER TABLE appointments
    ADD COLUMN IF NOT EXISTS slot_type        VARCHAR(10) NOT NULL DEFAULT 'exact',  -- exact | window
    ADD COLUMN IF NOT EXISTS session_id       INTEGER REFERENCES sessions(id),
    ADD COLUMN IF NOT EXISTS service_point_id INTEGER REFERENCES service_points(id),
    ADD COLUMN IF NOT EXISTS appointment_type VARCHAR(100),
    ADD COLUMN IF NOT EXISTS patient_category VARCHAR(50);
```
> `slot_type = 'exact'` = พฤติกรรมเดิม (นัดเวลาตรง), `'window'` = นัดช่วงเวลาแล้วจับคิวหน้างาน

### 4.4 `queue_entries` — แกนกลางของระบบคิว (รวม appointment + walk-in)
```sql
CREATE TABLE IF NOT EXISTS queue_entries (
    id               SERIAL PRIMARY KEY,
    appointment_id   INTEGER REFERENCES appointments(id),   -- NULL = walk-in
    service_point_id INTEGER NOT NULL REFERENCES service_points(id),
    session_id       INTEGER REFERENCES sessions(id),
    session_date     DATE NOT NULL,
    patient_ref      VARCHAR(100) NOT NULL,                 -- canonical ref: patient:{id} หรือ phone:{normalized_phone} (ห้ามใช้ชื่อ)
    entry_class      VARCHAR(20) NOT NULL DEFAULT 'walkin', -- appointment | walkin (effective หลัง grace)
    queue_number     INTEGER,                               -- ออกตอน check-in
    status           VARCHAR(20) NOT NULL DEFAULT 'checked_in',
                     -- checked_in | called | in_service | done | no_show | skipped
    priority_score   NUMERIC(10,3),                         -- cache ล่าสุด (nullable)
    check_in_at      TIMESTAMPTZ,
    called_at        TIMESTAMPTZ,
    service_start_at TIMESTAMPTZ,
    service_end_at   TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_queue_entries_active
    ON queue_entries (service_point_id, session_date, status);
CREATE INDEX IF NOT EXISTS idx_queue_entries_appt
    ON queue_entries (appointment_id);
```
> **timestamp 4 ตัว (check_in / called / service_start / service_end) คือฐานของทุกอย่าง** — ต้องเขียนให้ครบทุกครั้งที่สถานะเปลี่ยน ห้ามละเว้น

### 4.5 `queue_events` — append-only event log (ขับทั้ง display + analytics + ML อนาคต)
```sql
CREATE TABLE IF NOT EXISTS queue_events (
    id              BIGSERIAL PRIMARY KEY,
    queue_entry_id  INTEGER NOT NULL REFERENCES queue_entries(id),
    event_type      VARCHAR(40) NOT NULL,    -- check_in | call | start_service | end_service | no_show | reclass | skip
    from_status     VARCHAR(20),
    to_status       VARCHAR(20),
    actor           VARCHAR(20) NOT NULL DEFAULT 'system',  -- staff | system | patient
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata        JSONB
);
CREATE INDEX IF NOT EXISTS idx_queue_events_entry ON queue_events (queue_entry_id);
CREATE INDEX IF NOT EXISTS idx_queue_events_time  ON queue_events (occurred_at);
```
> **กฎ:** ทุกครั้งที่ `queue_entries.status` เปลี่ยน ต้อง insert `queue_events` หนึ่งแถวเสมอ (append-only, ห้าม update/delete)

### 4.6 `channel_links` — ผูก patient เข้ากับ messaging identity
```sql
CREATE TABLE IF NOT EXISTS channel_links (
    id           SERIAL PRIMARY KEY,
    patient_ref  VARCHAR(100) NOT NULL,
    channel      VARCHAR(20) NOT NULL,        -- line | telegram | pwa
    external_id  VARCHAR(255) NOT NULL,       -- LINE userId | Telegram chat_id | PWA subscription id
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    raw_profile  JSONB,
    linked_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (channel, external_id)
);
CREATE INDEX IF NOT EXISTS idx_channel_links_patient ON channel_links (patient_ref);
```
> PWA subscription (endpoint + keys) เก็บใน `raw_profile` (JSONB)

### 4.6.1 Identity resolution — `patient_ref` canonical (A) (บังคับ — notification พึ่งจุดนี้)
`notify()` (§5.6) หา channel จาก `channel_links` **ด้วย `patient_ref`** ถ้าค่าที่เขียนตอน booking/check-in ไม่ตรงกับค่าที่เขียนตอนผูก identity → join ไม่เจอ → push ไม่มีผู้รับ (ล้มเงียบ ไม่มี error) จึงต้องมี contract เดียวทั้งระบบ

**รูป canonical (ทุกตารางที่มี `patient_ref` ต้องใช้รูปนี้):**
- `patient:{id}` — เมื่อมี `patients.id` (ผู้ป่วยที่ระบุตัวตนได้)
- `phone:{normalized_phone}` — fallback สำหรับ guest/walk-in (normalize ก่อนเสมอให้คงรูปเดียว เช่น E.164 หรือตัด non-digit + เติม country code)
- **ห้ามใช้ชื่อเป็น key เด็ดขาด** (ไม่ unique, สะกดต่าง, ชนกันข้ามคน)

**กฎการผูก identity (`channel_links`):**
- ผูก `external_id` (LINE userId / Telegram chat_id / PWA subscription) ↔ `patient_ref` **เฉพาะตอนที่ยืนยันตัวตนได้** — หลักคือตอนเปิด Mini App แบบ authenticated (LIFF ID token verified / Telegram initData validated) ที่ผูกกับ booking/patient อยู่แล้ว หรือผ่าน flow ยืนยันเบอร์
- เคสที่ต้องระวัง: คนไข้จองทางโทรศัพท์แล้วค่อยแอด LINE OA ทีหลัง → ได้ `external_id` ที่ยัง map ไป `patient_ref` ไม่ได้ → **ห้ามเดา**
- **ถ้ายังไม่มี `patient_ref` ที่ยืนยันตัวตนได้:** notification ของคนนั้นเป็น **pull + log เท่านั้น** (ไม่ push) จนกว่าจะ link identity สำเร็จ — `notify()` ต้องเช็คเงื่อนไขนี้ก่อนเลือกช่อง push (ดู §5.6 Identity gate)
- `notification_log` / `queue_entries` ใช้ `patient_ref` รูปเดียวกัน เพื่อให้ dedupe (§5.6) และ join ทำงานข้ามตาราง

### 4.7 `messaging_config` — config การส่งข้อความต่อ tenant (1 แถวต่อ schema)
```sql
CREATE TABLE IF NOT EXISTS messaging_config (
    id                       SERIAL PRIMARY KEY,
    line_channel_id          VARCHAR(100),
    line_channel_secret_enc  TEXT,           -- ENCRYPTED
    line_channel_token_enc   TEXT,           -- ENCRYPTED
    line_login_channel_id    VARCHAR(100),   -- (เพิ่ม 15 มิ.ย. 2026) verify ID token จาก LIFF (aud = Login channel id)
    line_liff_id             VARCHAR(100),
    line_status              VARCHAR(20) NOT NULL DEFAULT 'not_configured', -- not_configured | active | error | disabled
    line_last_error          TEXT,
    telegram_bot_token_enc   TEXT,           -- ENCRYPTED
    telegram_bot_username    VARCHAR(100),
    telegram_bot_ownership   VARCHAR(10) NOT NULL DEFAULT 'saas',  -- (เพิ่ม 15 มิ.ย. 2026) saas | tenant — ดู §6.8
    telegram_webhook_secret_enc TEXT,        -- ENCRYPTED (เพิ่ม 15 มิ.ย. 2026) secret_token สำหรับ verify webhook
    telegram_mini_app_short_name VARCHAR(100),  -- (เพิ่ม 15 มิ.ย. 2026) direct link t.me/<user>/<shortname>; null=ใช้ fallback t.me/<bot>?start=
    telegram_status          VARCHAR(20) NOT NULL DEFAULT 'not_configured', -- not_configured | active | error | disabled
    telegram_last_error      TEXT,
    pwa_status               VARCHAR(20) NOT NULL DEFAULT 'disabled',       -- disabled | active | error
    pwa_vapid_public_key     TEXT,
    pwa_vapid_private_key_enc TEXT,         -- ENCRYPTED (per-tenant VAPID private key)
    plan_tier                VARCHAR(20) DEFAULT 'free',  -- free | light | standard
    channel_priority         JSONB NOT NULL DEFAULT '["telegram","pwa","line_push"]',
                             -- ลำดับช่องสำหรับ async notification (ถูก→แพง)
    reminder_enabled         BOOLEAN NOT NULL DEFAULT FALSE,  -- เปิดเตือนล่วงหน้า (อาจเสียเงิน)
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (telegram_bot_ownership IN ('saas', 'tenant')),
    CHECK (line_status IN ('not_configured', 'active', 'error', 'disabled')),
    CHECK (telegram_status IN ('not_configured', 'active', 'error', 'disabled')),
    CHECK (pwa_status IN ('disabled', 'active', 'error'))
);
```
> **`*_enc` ทุก column ต้องเข้ารหัสก่อนเก็บ** (เช่น Fernet / app-level encryption) — ห้าม plaintext
> **(F) ความสัมพันธ์ §4.7 ↔ Phase 4.0:** `CREATE TABLE` ด้านบนคือ **target final schema** — tenant/schema ที่สร้าง messaging_config "ใหม่" (รวม Phase 0 ของ tenant ใหม่) ให้สร้างด้วยรูปนี้ครบทุก column ส่วน **Phase 4.0 = upgrade migration เฉพาะ tenant/table ที่ถูกสร้างไปแล้วก่อน 15 มิ.ย. 2026** (ยังไม่มี column ชุดนี้) — ใช้ ALTER ด้านล่างแบบ idempotent (`ADD COLUMN IF NOT EXISTS`) จึงรันซ้ำกับ table ที่ครบแล้วได้โดยเป็น no-op ไม่ขัดกัน
> ```sql
> ALTER TABLE messaging_config
>     ADD COLUMN IF NOT EXISTS line_login_channel_id        VARCHAR(100),
>     ADD COLUMN IF NOT EXISTS line_status                  VARCHAR(20) NOT NULL DEFAULT 'not_configured',
>     ADD COLUMN IF NOT EXISTS line_last_error              TEXT,
>     ADD COLUMN IF NOT EXISTS telegram_bot_ownership       VARCHAR(10) NOT NULL DEFAULT 'saas',
>     ADD COLUMN IF NOT EXISTS telegram_webhook_secret_enc  TEXT,
>     ADD COLUMN IF NOT EXISTS telegram_mini_app_short_name VARCHAR(100),
>     ADD COLUMN IF NOT EXISTS telegram_status              VARCHAR(20) NOT NULL DEFAULT 'not_configured',
>     ADD COLUMN IF NOT EXISTS telegram_last_error          TEXT,
>     ADD COLUMN IF NOT EXISTS pwa_status                   VARCHAR(20) NOT NULL DEFAULT 'disabled',
>     ADD COLUMN IF NOT EXISTS pwa_vapid_public_key         TEXT,
>     ADD COLUMN IF NOT EXISTS pwa_vapid_private_key_enc    TEXT;
> ```
> - `line_login_channel_id`: ID token จาก LIFF มี `aud` = **Login channel id** → ต้องใช้ค่านี้ verify (ไม่ใช่ Messaging API channel id)
> - `telegram_bot_ownership`: `saas` (SaaS ถือ/จัดการ bot) หรือ `tenant` (โรงพยาบาลสร้าง bot เอง มอบ token ให้) — **runtime ใช้ token เหมือนกัน**, flag กระทบแค่ provisioning + lifecycle (ดู §6.8)
> - `telegram_webhook_secret_enc`: secret_token ที่ส่งตอน setWebhook → เทียบ header `X-Telegram-Bot-Api-Secret-Token`; plaintext ก่อน encrypt ต้องยาว 1–256 ตัว และใช้เฉพาะ `A-Z a-z 0-9 _ -`
> - `line_status` / `telegram_status` / `pwa_status`: dispatcher ถือว่า channel ใช้ได้เฉพาะ `active`; token/webhook fail ให้ตั้ง `error` + `*_last_error`; tenant ปิดเองให้ตั้ง `disabled`
> - `pwa_vapid_private_key_enc`: private key ของ Web Push ต้อง encrypt; public key เก็บ plaintext ได้
> - migration จริงต้องเพิ่ม CHECK constraints แบบ idempotent (เช่น `DO $$ BEGIN ... EXCEPTION WHEN duplicate_object THEN NULL; END $$;`) เพราะ PostgreSQL ไม่มี `ADD CONSTRAINT IF NOT EXISTS`

### 4.8 `notification_log` — log ทุกการแจ้งเตือน (วิเคราะห์ต้นทุน + กันแจ้งซ้ำ)
```sql
CREATE TABLE IF NOT EXISTS notification_log (
    id             BIGSERIAL PRIMARY KEY,
    queue_entry_id INTEGER REFERENCES queue_entries(id),
    patient_ref    VARCHAR(100),
    event_type     VARCHAR(40) NOT NULL,    -- booking_confirm | checkin_confirm | queue_near | queue_turn | reminder
    channel        VARCHAR(20) NOT NULL,    -- line_push | line_reply | liff | telegram | pwa | pull
    cost_units     SMALLINT NOT NULL DEFAULT 0,   -- 0 = ฟรี, 1 = นับ 1 ข้อความ
    status         VARCHAR(20) NOT NULL,    -- sent | failed | skipped
    sent_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    error          TEXT,
    metadata       JSONB
);
CREATE INDEX IF NOT EXISTS idx_notif_log_time ON notification_log (sent_at);
CREATE INDEX IF NOT EXISTS idx_notif_log_dedupe
    ON notification_log (patient_ref, event_type, status, sent_at);
```

### 4.9 `queue_policy` — นโยบายการเรียกคิว (ต่อ service_point หรือ default ของ tenant)
```sql
CREATE TABLE IF NOT EXISTS queue_policy (
    id                            SERIAL PRIMARY KEY,
    service_point_id              INTEGER REFERENCES service_points(id),  -- NULL = default ของ tenant
    mode                          VARCHAR(10) NOT NULL DEFAULT 'ratio',   -- ratio | score
    -- โหมด ratio:
    appointment_to_walkin_ratio   SMALLINT NOT NULL DEFAULT 3,            -- เรียกนัด 3 : walk-in 1
    walkin_max_wait_minutes       INTEGER NOT NULL DEFAULT 45,            -- starvation guard
    appointment_early_eligible_minutes INTEGER NOT NULL DEFAULT 15,       -- เรียกนัดได้ก่อน slot กี่นาที
    call_timeout_min              INTEGER NOT NULL DEFAULT 5,             -- (D) เรียกแล้วไม่ขึ้น in_service ภายในกี่นาที -> ปิด stale called คืน capacity
    -- โหมด score (weights):
    w_class                       NUMERIC(6,3) NOT NULL DEFAULT 100,
    w_wait                        NUMERIC(6,3) NOT NULL DEFAULT 1,
    w_window                      NUMERIC(6,3) NOT NULL DEFAULT 2,
    updated_at                    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 4.10 `grace_policy` — นโยบาย grace rule (ต่อ service_point หรือ default)
```sql
CREATE TABLE IF NOT EXISTS grace_policy (
    id                       SERIAL PRIMARY KEY,
    service_point_id         INTEGER REFERENCES service_points(id),  -- NULL = default
    grace_before_min         INTEGER NOT NULL DEFAULT 30,    -- มาก่อนนัดกี่นาที ยังถือ priority เต็ม
    grace_after_min          INTEGER NOT NULL DEFAULT 30,    -- มาหลังนัดกี่นาที ยังถือ priority เต็ม
    late_arrival_policy      VARCHAR(20) NOT NULL DEFAULT 'demote_to_walkin',
                             -- demote_to_walkin | reslot_to_current | require_rebook
    no_show_grace_min        INTEGER NOT NULL DEFAULT 10,    -- รอก่อนปล่อย capacity
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 4.11 Control-plane tables (`public` schema — ไม่ใช่ tenant schema) — สำหรับ Telegram Model A เท่านั้น
> ใช้เฉพาะ **Model A (SaaS-managed bot, §6.8)** เพื่อจัดการ pool ของ Telegram account (ลิมิต ~20 bot/account)
> **Model B (tenant BYO) ไม่ต้องลงตารางนี้** — bot อยู่ account ของโรงพยาบาลเอง
> **ทำเมื่อจำเป็น** (SaaS-managed + tenant เริ่มเยอะ) — แต่แม้มี account เดียว registry ก็มีประโยชน์ไว้ track ว่า bot ไหนของ tenant ไหน

```sql
-- registry ของ Telegram account ที่ SaaS ใช้ host bot
CREATE TABLE IF NOT EXISTS public.saas_telegram_accounts (
    id            SERIAL PRIMARY KEY,
    label         VARCHAR(100) NOT NULL UNIQUE,           -- ชื่ออ้างอิง ops เช่น 'saas-tg-01'
    bot_capacity  SMALLINT NOT NULL DEFAULT 20,           -- ลิมิต bot/account (ปรับได้ถ้า Telegram เพิ่มให้)
    status        VARCHAR(10) NOT NULL DEFAULT 'active',  -- active | full | disabled
    contact_note  TEXT,                                   -- หมายเหตุ ops (อย่าเก็บเบอร์/credential เป็น plaintext — ใช้ password manager)
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (bot_capacity > 0),
    CHECK (status IN ('active', 'full', 'disabled'))
);

-- allocation: bot → account → tenant (token จริงอยู่ที่ tenant.messaging_config ไม่ซ้ำที่นี่)
CREATE TABLE IF NOT EXISTS public.saas_telegram_bots (
    id              SERIAL PRIMARY KEY,
    saas_account_id INTEGER NOT NULL REFERENCES public.saas_telegram_accounts(id),
    tenant_schema   VARCHAR(63) REFERENCES public.hospitals(schema_name), -- NULL = spare ยังไม่ allocate
    bot_username    VARCHAR(100) NOT NULL UNIQUE, -- ไม่ใช่ secret (token อยู่ messaging_config.telegram_bot_token_enc)
    status          VARCHAR(10) NOT NULL DEFAULT 'allocated',  -- allocated | spare | revoked
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status IN ('allocated', 'spare', 'revoked'))
);
CREATE INDEX IF NOT EXISTS idx_saas_tg_bots_account ON public.saas_telegram_bots (saas_account_id);
CREATE INDEX IF NOT EXISTS idx_saas_tg_bots_tenant  ON public.saas_telegram_bots (tenant_schema);
CREATE UNIQUE INDEX IF NOT EXISTS uq_saas_tg_bots_allocated_tenant
    ON public.saas_telegram_bots (tenant_schema)
    WHERE tenant_schema IS NOT NULL AND status = 'allocated';
```

**กฎ:**
- **เก็บเฉพาะ metadata — ห้ามเก็บ bot token ที่นี่** (token อยู่ encrypt ที่ tenant `messaging_config.telegram_bot_token_enc`); registry นี้ track ownership/allocation เท่านั้น
- **ห้ามเก็บเบอร์/credential ของ Telegram account เป็น plaintext** — `label`/`contact_note` เป็นแค่อ้างอิง ops, credential เก็บใน password manager
- capacity check: `COUNT(saas_telegram_bots WHERE status='allocated')` ต่อ account เทียบ `bot_capacity`
- **bot สร้างแบบ on-demand** ตอน onboard tenant (ไม่ pre-create spare pool) — ถ้าจะทำ spare pool ต้องเก็บ token ของ spare ไว้ที่ไหนสักที่ที่ encrypt (ซับซ้อนขึ้น) → แนะนำ on-demand ก่อน

**Allocation helper (control-plane, Python):** ไฟล์เสนอ `flask_app/app/services/telegram_pool.py`
```python
def allocate_account() -> "SaasTelegramAccount":
    """
    คืน account ที่ status='active' และ count(allocated bots) < bot_capacity
    ไม่มี -> raise PoolExhausted (ต้องเพิ่ม saas_telegram_accounts ใหม่)
    ใช้ตอน onboard Model A: เลือก account ที่จะไปสร้าง bot
    """

def register_bot(saas_account_id: int, tenant_schema: str, bot_username: str) -> None:
    """หลัง ops สร้าง bot ใน account นั้นแล้ว: insert allocation row (Model A)
    re-check capacity แบบ atomic ตอน insert (COUNT allocated < bot_capacity ใต้ row lock ของ account)
    กัน race ระหว่าง allocate_account() กับ register_bot() (สอง onboarding allocate account เดียวกันจนเกิน capacity)"""
```
> flow Model A: `allocate_account()` → ops สร้าง bot ใน account นั้น (BotFather) → `register_bot()` → `provision_telegram_bot()` เก็บ token ใน tenant `messaging_config`

---

## 5. Component Specifications (Python contracts)

> เขียนเป็น Python ทั้งหมด (Flask-first). โครงด้านล่างคือ **contract/interface** — agent implement รายละเอียดได้ แต่ต้องรักษา signature และพฤติกรรมที่ระบุ

### 5.1 Queue state machine helper
ไฟล์เสนอ: `flask_app/app/services/queue_service.py`

```python
def transition(entry_id: int, to_status: str, actor: str = 'system',
               metadata: dict | None = None) -> None:
    """
    เปลี่ยนสถานะ queue_entry + เขียน queue_events 1 แถว (append-only) + set timestamp ที่เกี่ยวข้อง
    - to_status='called'        -> set called_at
    - to_status='in_service'    -> set service_start_at
    - to_status='done'          -> set service_end_at
    - to_status='no_show'/'skipped' -> ปิด entry
    ต้องทำใน transaction เดียว (update entry + insert event) ห้ามแยก
    ห้ามลืม insert queue_events ทุกครั้ง
    """
```

### 5.2 Check-in + queue number assignment
```python
def check_in(appointment_id: int | None, service_point_id: int,
             patient_ref: str, now: datetime) -> QueueEntry:
    """
    - ถ้ามี appointment_id: เรียก grace_service.classify_on_checkin() เพื่อกำหนด entry_class
    - ถ้าไม่มี (walk-in): entry_class = 'walkin'
    - assign queue_number = running ต่อ (service_point_id, session_date) [ดูหมายเหตุ concurrency]
    - สร้าง queue_entry (status='checked_in', set check_in_at) + queue_events('check_in')
    - return entry
    """
```
> **Concurrency (E):** การ assign `queue_number` ต้องกัน race (สแกน QR พร้อมกัน) **ห้ามใช้ `MAX()+1` แบบ non-atomic** และ **อย่าใช้ "DB sequence ต่อ (service_point, date)"** (Postgres sequence เป็น schema object สร้างต่อคู่ (sp,date) ไม่ได้จริง — งอกไม่จำกัด/ตามลบยาก) ทางที่ atomic: **(แนะนำ) counter table** `queue_counters(service_point_id, session_date, last_number)` แล้ว `UPDATE ... SET last_number = last_number + 1 WHERE ... RETURNING last_number` (row lock อะตอมมิกในตัว + upsert สำหรับเลขแรก) **หรือ** advisory xact lock ต่อ (service_point, date) ครอบ `MAX()+1`

### 5.3 Grace rule engine
ไฟล์เสนอ: `flask_app/app/services/grace_service.py`

```python
# แก้ 13 มิ.ย. 2026 (C): pseudocode นี้ใช้ชื่อย่อ — คอลัมน์จริงใน grace_policy คือ
#   grace_before_min / grace_after_min (ดู §4.10); และ service จริงรับ `db` เป็น arg ตัวแรก
#   (เช่น classify_on_checkin(db, appointment, now, policy)). slot_start/slot_end ไม่มีในตาราง —
#   ใช้ appointment.start_time/end_time (A1 §12 ตัดสินแล้ว: ทุกนัดเป็น exact)
def classify_on_checkin(appointment, now: datetime, policy: GracePolicy) -> str:
    """
    คืนค่า entry_class:
    - ถ้า now อยู่ในช่วง [slot_start - grace_before_min, slot_end + grace_after_min] -> 'appointment' (priority เต็ม)
    - ถ้า now อยู่ session เดียวกันแต่นอกช่วง grace -> ตาม late_arrival_policy:
        demote_to_walkin   -> 'walkin'
        reslot_to_current  -> ย้าย session_id เป็น current + 'appointment'
        require_rebook      -> raise NoShowError (ต้องจองใหม่)
    - ถ้าข้าม session ในวันเดียวกัน -> ตาม late_arrival_policy เช่นกัน (demote เป็น default)
    เมื่อ reclass ให้ insert queue_events('reclass') ด้วย
    """
```
> default behavior ที่ต้องการ: ในช่วง → priority เต็ม; วันเดียวกันนอกช่วง → demote เป็น walk-in; ไม่มาจนปิด → no_show (job แยก)
> **No-show sweeper:** background/cron ต่อ tenant: entries status='checked_in' ที่ผ่านเกณฑ์ (เลยเวลาปิด session / เกิน no_show_grace_min หลังถูกข้าม) -> set 'no_show' + event
> **(D) Stale `called` timeout:** entries status='called' ที่ `called_at + call_timeout_min` (§4.9) ผ่านไปแล้วยังไม่ขึ้น 'in_service' -> ปิดเป็น 'no_show' (หรือ 'skipped' ตาม policy) + event เพื่อ **คืน capacity** — capacity rule (§5.4) นับ called+in_service ถ้าไม่ปิด stale called ช่อง server จะรั่วจน `call_next` คืน None ตลอด (คิว deadlock); ให้ทำใน sweeper **และ** เป็น preflight ต้น `call_next` (ปิด stale ก่อนคำนวณ outstanding)

### 5.4 Queue priority engine
ไฟล์เสนอ: `flask_app/app/services/priority_service.py`

```python
def call_next(service_point_id: int, now: datetime) -> QueueEntry | None:
    """
    หา entry ถัดไปที่จะเรียก:
    1. candidates = entries(status='checked_in', service_point=sp) ที่ eligible:
       - walk-in: eligible เสมอ
       - appointment: eligible เมื่อ now >= slot_start - appointment_early_eligible_minutes
    2. ถ้าไม่มี server ว่าง -> return None
       **(D) preflight:** ก่อนนับ outstanding ให้ปิด stale 'called' (called_at + call_timeout_min เกิน) เป็น no_show/skipped + event ก่อน (กัน capacity รั่ว — ดู §5.3)
       **capacity rule (ปรับ 13 มิ.ย. 2026):** outstanding = นับ **called + in_service** (ไม่ใช่แค่ in_service)
       เทียบ parallel_servers — เพราะคนสถานะ 'called' ถูกเรียกแล้วกำลังเดินมาหา server จึงกินช่องอยู่
       ถ้านับแค่ in_service เจ้าหน้าที่ดับเบิลคลิก/กดพร้อมกันจะเรียกเกินจำนวน server ได้
    3. mode == 'ratio' -> pick_by_ratio(candidates, recent_call_history, policy)
       mode == 'score' -> max(candidates, key=compute_priority_score)
    4. ถ้า server ว่าง + มี candidate -> เรียกได้แม้ยังไม่ครบ ratio (กัน idle)
    **concurrency:** ต้อง serialize call_next ต่อ service_point (advisory xact lock) ให้ step 2-4 atomic
    มิฉะนั้น capacity check แข่งกันเอง (สอง request อ่าน outstanding=0 พร้อมกันแล้วเรียกทั้งคู่)
    Phase 1 (queue_service.call_next) ทำตามกฎนี้แล้ว — Phase 2.3 (priority_service) ต้องคงไว้
    คืน entry ที่ควรเรียก (ยังไม่ transition — ให้ caller เรียก transition('called'))
    """

def compute_priority_score(entry, policy: QueuePolicy, now: datetime) -> float:
    class_rank = 2.0 if entry.entry_class == 'appointment' else 1.0
    minutes_waited = max(0, (now - entry.check_in_at).total_seconds() / 60)
    window_proximity = _window_proximity(entry, now)   # 0..1+ ตาม slot ใกล้/ถึง; คืน 0.0 ถ้า entry_class != 'appointment' (walk-in/demoted ไม่ได้ window bonus) — implemented แล้ว
    return (policy.w_class * class_rank
            + policy.w_wait * minutes_waited
            + policy.w_window * window_proximity)
```
> **pick_by_ratio:** ดู call history ล่าสุดของ session ถ้าเรียก appointment ติดกันครบ `appointment_to_walkin_ratio` แล้วและมี walk-in รออยู่ -> เรียก walk-in คนที่รอนานสุด มิฉะนั้นเรียก appointment ที่ eligible และ slot ใกล้สุด
> **starvation guard (ทั้งสอง mode):** walk-in ที่ waited > `walkin_max_wait_minutes` ต้องถูกดันขึ้นก่อน (ใน score mode ค่านี้จะสูงเองจาก w_wait, แต่ใส่ hard override ไว้ด้วยเพื่อความแน่นอน)

### 5.5 Wait-time estimator (strategy pattern — seam สำคัญสุดของ Q3)
ไฟล์เสนอ: `flask_app/app/services/estimation/`

```python
# estimation/base.py
class WaitEstimator(Protocol):
    def estimate(self, entry: QueueEntry, now: datetime) -> EstimateResult: ...

@dataclass
class EstimateResult:
    wait_minutes: float
    people_ahead: int
    method: str          # 'simple_avg' | 'erlang_c' | 'ml' ...
    confidence: str = "approx"

# estimation/simple_avg.py  (LEVEL 1-2 — implement ตอนนี้)
class SimpleAverageEstimator:
    def estimate(self, entry, now):
        # แก้ 13 มิ.ย. 2026 (C): helper จริงใน queue_service มี signature
        #   count_ahead(db, service_point_id, session_date, queue_number) — ไม่ใช่ count_ahead(entry)
        #   (ดึง field จาก entry มาส่งเอง); next_in_line(db, service_point_id, session_date) ก็มีให้ใช้
        ahead   = count_ahead(entry)                       # คนสถานะ checked_in/called ที่อยู่ก่อน
        servers = entry.service_point.parallel_servers
        avg     = rolling_service_time(entry.service_point_id, now, pct=80)  # p80 minutes
        wait    = (ahead / max(servers, 1)) * avg
        return EstimateResult(wait_minutes=wait, people_ahead=ahead, method='simple_avg')

# factory
def get_estimator(tenant_config) -> WaitEstimator:
    # ตอนนี้คืน SimpleAverageEstimator เสมอ
    # อนาคต: switch ตาม config เป็น ErlangCEstimator / MLEstimator โดยไม่แตะ caller
    return SimpleAverageEstimator()
```
- **กฎสำคัญ:** ทุกที่ในระบบ **ต้องเรียกผ่าน `get_estimator(...).estimate(...)`** เท่านั้น ห้ามคำนวณ wait แบบ inline ที่อื่น (เพื่อให้สลับ algorithm ได้ทีหลัง)
- ใช้ **p80 (หรือ p50)** ไม่ใช่ mean — ประมาณเผื่อนานกว่าจริงดีกว่าสั้นกว่าจริง
- `rolling_service_time`: คำนวณจาก `service_end_at - service_start_at` ของ entries ที่ done ย้อนหลัง แยกตาม service_point (+ วัน/ช่วงเวลาถ้าข้อมูลพอ)
- **(C) Cold-start fallback (บังคับ):** วันแรก/service_point ใหม่ไม่มี done sample → percentile ของ empty set ใช้ไม่ได้ ต้อง fallback `DEFAULT_SERVICE_MINUTES = 10.0` (implemented แล้วใน code) — แผนยึดค่านี้เป็น default; ปรับให้ดีขึ้นภายหลังได้: ทำ `DEFAULT_SERVICE_MINUTES` เป็น config ต่อ service_point/event_type + ตั้ง **min-sample threshold** (เช่น ต้องมี done ≥ N ถึงใช้ค่าจริง ไม่งั้น blend กับ default) กัน estimate กระโดดตอน sample น้อย
- **(B) ข้อจำกัด — estimator ยังไม่ priority-aware:** ตอนนี้ `count_ahead` นับคน "ที่อยู่ก่อน" ตาม **`queue_number` (positional)** แต่ลำดับเรียกจริงตัดสินด้วย priority engine (§5.4 ratio/score) ผลคือ **walk-in จะถูก under-estimate** (นัดแซงเรื่อย ๆ เวลารอจริงนานกว่าที่บอก — อันตราย คนไข้อาจเดินออกแล้วพลาดคิว) ส่วน appointment holder จะ over-estimate (ไม่อันตราย) p80 เผื่อ noise ของ service time แต่ไม่แก้ปัญหา ordering นี้ → **future work (level 3):** ทำ `count_ahead` ให้ class-aware (นับเฉพาะคนที่จะถูกเรียกก่อนจริงตามกฎ ratio/score) โดยไม่แตะ caller (ผ่าน factory §5.5); จนกว่าจะแก้ ให้ถือว่าเลขที่โชว์เป็น "ประมาณคร่าว" และระวัง under-estimate walk-in

### 5.6 Notification dispatcher (หัวใจการคุมต้นทุน — ส่วนที่ 6)
ไฟล์เสนอ: `flask_app/app/services/notify_service.py`

```python
def notify(patient_ref: str, event_type: str, urgency: str,
           context: dict, reply_token: str | None = None) -> None:
    """
    urgency: 'critical' (ใกล้/ถึงคิว) | 'normal' | 'low'
    - โหลด messaging_config (tenant) + channel_links (patient)
    - เลือกช่องตามกฎใน 6.2:
        * ถ้ามี reply_token (อยู่ใน webhook context) และ event ตอบสนอง user action -> LINE reply (ฟรี)
        * async + urgency='critical' -> ตาม channel_priority (telegram/pwa ฟรีก่อน, แล้ว line_push เสียเงิน)
        * async + urgency='low' (เช่น reminder) -> ส่งเฉพาะถ้า reminder_enabled, เลือกช่องฟรีก่อน
    - ส่งจริง แล้ว insert notification_log (channel, cost_units, status)
    - fallback ช่องถัดไปถ้า fail
    - ห้ามส่งซ้ำ event เดิม patient เดิมภายในกรอบเวลาสั้น (กันสแปม) -> เช็ค notification_log
    - dedupe check + send + log ต้องอยู่ใต้ advisory xact lock ต่อ
      (current_schema(), patient_ref, event_type) เพื่อกัน TOCTOU double-push
    """
```
> `liff.sendMessages` เป็น client-side (ไม่ผ่าน dispatcher) — ใช้ในหน้า LIFF ตอน user เพิ่งทำ action เพื่อยืนยันแบบฟรี
> **(H) Sync vs async — ล็อกแล้ว:** event `queue_turn` / `queue_near` (critical) **ต้อง enqueue ผ่าน worker/RQ เท่านั้น ห้ามส่ง sync ใน request ของ staff console** (LINE/Telegram API ช้า/ล่ม จะทำให้ปุ่ม "เรียกคิว" ค้างหรือ error) — `call_next` แค่ transition + enqueue งาน notify แล้ว return ทันที; **worker process ต้องโหลด `MESSAGING_ENCRYPTION_KEYS` ตัวเดียวกัน** (ดู §5.7) และ import `notify_service` ได้ (อยู่ใต้ `flask_app/app/services/` — ยืนยัน PYTHONPATH ของ worker)
> **(A) Identity gate (บังคับ):** ก่อนเลือกช่อง push ต้องมี `patient_ref` ที่ยืนยันตัวตน + `channel_links` ที่ active (ดู §4.6.1) ถ้ายังไม่ link → ห้าม push ให้ log สถานะ 'skipped' (เหตุผล: no linked identity) แล้วพึ่ง pull แทน

### 5.7 Encryption helper สำหรับ token/secret (security — บังคับ)
ไฟล์จริง: `shared_db/crypto.py` (ใช้ร่วมกันทั้ง Flask, FastAPI, worker; ห้ามสร้าง helper ซ้ำใน `flask_app/app/utils/`)

ใช้ **Fernet (symmetric)** จาก library `cryptography` encrypt column `*_enc` ทุกตัวใน `messaging_config` (LINE channel secret/token, Telegram bot token) — เลือก Fernet เพราะง่าย, ปลอดภัยพอสำหรับ app-level secret, และ `MultiFernet` รองรับ key rotation ในตัว

```python
# shared_db/crypto.py
import os
from cryptography.fernet import Fernet, MultiFernet

def _cipher() -> MultiFernet:
    # MESSAGING_ENCRYPTION_KEYS = base64 keys คั่นด้วย comma
    # key ตัวแรก = key ปัจจุบัน (ใช้ encrypt), ที่เหลือไว้ decrypt ตอน rotate
    raw = os.environ["MESSAGING_ENCRYPTION_KEYS"]
    return MultiFernet([Fernet(k.strip().encode()) for k in raw.split(",") if k.strip()])

def encrypt(plaintext: str | None) -> str | None:
    if plaintext is None:
        return None
    return _cipher().encrypt(plaintext.encode()).decode()

def decrypt(ciphertext: str | None) -> str | None:
    if ciphertext is None:
        return None
    return _cipher().decrypt(ciphertext.encode()).decode()
```

**กฎ key management (สำคัญ — ทำผิด = tenant ทุกรายต้อง re-link ใหม่):**
- generate key ด้วย `Fernet.generate_key()` (ครั้งเดียว ตอน setup)
- เก็บใน **env var / secrets manager เท่านั้น** — ห้ามอยู่ใน repo, ห้ามอยู่ใน DB, ห้าม hardcode
- **process ทั้ง Flask (5001), FastAPI และ worker (RQ) ต้องโหลด `MESSAGING_ENCRYPTION_KEYS` ตัวเดียวกัน** ไม่งั้น decrypt ข้าม process ไม่ได้ (worker ส่ง push async ตาม §5.6/H จึงต้องถอด token ได้)
- **backup key อย่างปลอดภัย** — key หาย = decrypt token ทุก tenant ไม่ได้ = ทุกโรงพยาบาลต้องผูก LINE/Telegram ใหม่หมด
- **key rotation:** ใส่ key ใหม่ไว้ "หน้าสุด" ของ `MESSAGING_ENCRYPTION_KEYS` → MultiFernet encrypt ด้วยตัวใหม่ แต่ decrypt ของเก่ายังได้ → รัน background re-encrypt ทุกแถว → แล้วค่อยถอด key เก่าออก
- decrypt เฉพาะตอนจะใช้จริงใน dispatcher — **ห้าม log ค่า plaintext ที่ไหนเลย**

> **ทางเลือก production (optional):** ถ้าโตขึ้น ให้ย้าย token ทั้งหมดไป secrets manager (AWS Secrets Manager / GCP Secret Manager / Vault) แล้วเก็บแค่ reference ใน DB — แต่ Fernet-in-DB เป็นจุดเริ่มที่ดีพอแล้ว

### 5.8 Session generator (materialize sessions จาก availability template)
ไฟล์เสนอ: `flask_app/app/services/session_service.py`

> **Prerequisite resolved (ทำแล้ว 13 มิ.ย. 2026):** ตรวจ schema `availabilities` + `date_overrides` แล้ว และตัดสินใจ mapping ระหว่าง service_point กับ availability template แล้ว
> **ตัดสินใจแล้ว:** เพิ่ม column `service_points.availability_template_id` FK ไป **`availability_templates(id)`** (ไม่ใช่ `availabilities(id)` — `availabilities` คือ slot รายวันที่ผูกกับ template, ส่วน `availability_templates` คือตัว template จริง). many service_points : one template ได้
> ```sql
> -- FK ไป availability_templates (ตัว template จริง) — implemented แล้วใน migration Phase 1B
> ALTER TABLE service_points
>     ADD COLUMN IF NOT EXISTS availability_template_id INTEGER REFERENCES availability_templates(id);
> ```

**หลักการ:** "session" = การ materialize availability (template + date_overrides) ให้เป็นแถวจริงต่อวันต่อ service_point — เลือก **materialize** (ไม่ใช่ compute on-the-fly) เพราะ `queue_entries` ต้อง FK ไป session และต้องมี queue state คงที่ต่อ session

**ตอบคำถาม "ใช้ time slot เดิมได้ไหม": ใช้ได้ และคือสิ่งที่ตั้งใจ — time slot ที่ตั้งไว้ในระบบคือ source ของ session ไม่ต้องตั้งค่าซ้ำ** มีเรื่อง granularity ที่ต้องเลือก (ทำเป็น config ต่อ service_point):
- **แบบ A — session = time slot เดิมโดยตรง** (1 slot = 1 session): เหมาะกับ window ที่ละเอียด เช่น slot ละ 30 นาที แล้วจับคิวภายในแต่ละ slot
- **แบบ B — session = กลุ่มของ slot** (เช่น รวม slot ช่วงเช้าทั้งหมดเป็น session "เช้า" เดียว): start/end/capacity คำนวณจาก slot ที่อยู่ในกลุ่ม — เหมาะกับรูปแบบ "นัดช่วงเช้า แล้วจับคิว" ที่คุณต้องการ
- **`slot_type='exact'`** (พฤติกรรมเดิม): ไม่จำเป็นต้องมี session — appointment ใช้เวลานัดตรงได้เลย, `session_id` เป็น null ได้; session มีไว้สำหรับ `slot_type='window'` เป็นหลัก

> สรุปความสัมพันธ์: availability template / time slot = "กฎที่ตั้งไว้" (recurring) → `sessions` = "instance จริงต่อวันต่อจุดบริการ" ที่ generate จากกฎนั้น (แบบ A หรือ B) → `queue_entries` ผูกกับ session เพื่อจับคิว generator แค่อ่าน slot ที่มีอยู่ ไม่ได้สร้าง config ชุดใหม่

```python
# implement แล้ว 13 มิ.ย. 2026 — flask_app/app/services/session_service.py
# แก้ (C) จาก contract เดิม:
#   - signature จริงรับ `db` ตัวแรก: generate_sessions(db, service_point_id, date_from, date_to)
#   - session.name จริง = "HH:MM-HH:MM" ของบล็อก (stable/unique → idempotent + รองรับ multi-block)
#     ไม่ใช่ 'เช้า'/'บ่าย' (บล็อกเต็มวัน/หลายบล็อกจะชน UNIQUE + พัง idempotency)
#   - guard ใช้ queue_entries **และ** appointments (ดู _has_references) ไม่ใช่แค่ queue_entries
#   - step 3 override: booking.py:628-633 ทำ REPLACE (custom hours แทนตารางปกติทั้งวัน) →
#     เปิด "วันทำงานพิเศษ" ที่ปกติปิดได้ generator ทำตามนี้แล้ว (ดู A2 §12 — ตัดสินแล้ว)
def generate_sessions(service_point_id: int, date_from: date, date_to: date) -> list["Session"]:
    """
    resolve availability ที่ effective ของแต่ละวันในช่วง [date_from, date_to]:
      1. ดึง availability template ของ service_point (ผ่าน availability_template_id)
      2. apply weekly pattern -> ได้ session block (name, start_time, end_time, capacity) ต่อวัน
      3. apply date_overrides (template-specific ก่อน แล้ว fallback global legacy) ทับ -> REPLACE/ปิดวันนั้น (custom hours แทนทั้งวัน, เปิดวันพิเศษได้)
    UPSERT เข้า sessions (UNIQUE service_point_id, session_date, name) -> idempotent
    ห้ามลบ/แก้ session ที่มี queue_entries/appointment อยู่แล้ว (รักษา history)
    """

def sync_sessions_rolling(days_ahead: int = 14) -> None:
    """
    background job ต่อ tenant: regenerate sessions ช่วง [today, today + days_ahead]
    สำหรับทุก service_point ที่ active
    เรียกเมื่อ: (ก) รายวัน (scheduler)  (ข) ตอน availability/override ถูก save (trigger จาก availability_routes)
    """
```

**กฎที่ต้องรักษา:**
- **Idempotent:** UPSERT เท่านั้น รันซ้ำต้องไม่เกิดแถวซ้ำ
- **History preservation:** session ที่มี queue_entries แล้ว ห้ามลบ/แก้เวลา (sync เฉพาะ session อนาคตที่ยังว่าง)
- **Change propagation:** แก้ availability/override → re-sync เฉพาะ session อนาคต ไม่แตะอดีต
- **TeamUp:** ถ้า calendar บางตัวใช้ TeamUp เป็น source of truth ให้ generator อ่าน TeamUp events ประกอบด้วย (เป็น sub-task ภายหลังได้)

---

## 6. การเชื่อมต่อ LINE / Telegram / PWA

### 6.0 Channel parity matrix (LINE ↔ Telegram) — ต้องทำครบทั้งสองช่อง
| ความสามารถ | LINE | Telegram | หมายเหตุ |
|---|---|---|---|
| Account ต่อ tenant | Official Account (channel) | Bot (BotFather) | brand แยกต่อโรงพยาบาล |
| Mini app (หน้า web ในแอป) | LIFF / LINE MINI App | Telegram Mini App | หน้า Jinja2 เดิมตัวเดียวกัน + SDK ต่างกัน |
| Verify ตัวตนฝั่ง server | verify ID token | validate initData (HMAC) | **ห้ามเชื่อ client ดิบ** |
| เมนูถาวรเข้าแอป | Rich Menu | Menu Button (`setChatMenuButton`) + commands | ฟรีทั้งคู่ |
| QR check-in | QR → LIFF URL + param | QR → direct Mini App `?startapp=` หรือ fallback bot deep link `?start=` | encode `service_point_id` |
| Webhook | ตั้งใน console + verify signature | ตั้งด้วย `setWebhook` API | route ต่อ tenant |
| ยืนยันแบบฟรี | `liff.sendMessages` (มี caveat) | bot message ปกติ (ฟรีเสมอ) | Telegram ง่ายกว่า |
| ตอบ sync ฟรี | reply message (reply token) | bot message (ฟรีเสมอ) | — |
| Push async | **เสียเงิน** | **ฟรี** | Telegram ไม่มีค่าต่อข้อความ |
| แจ้งเตือน critical | line_push (เสียเงิน) | bot message (ฟรี) | ดัน Telegram ก่อน LINE |

> สรุป: **Telegram ทำได้ทุกอย่างที่ LINE ทำ และ "ฟรี" กว่า** (ไม่มี per-message cost, ไม่มี sync/async split) ความต่างเชิง implement อยู่ที่ SDK และวิธี register เท่านั้น

### 6.1 ตารางต้นทุน LINE (ของจริง ปี 2026, ไทย)
| แพ็กเกจ | ค่ารายเดือน | ข้อความฟรี/เดือน |
|---|---|---|
| Free (Communication) | ฟรี | 200 |
| Light | 599 บาท | 4,000 |
| Standard | 1,599 บาท | 10,000 |

- ข้อความเกินโควตา: ~0.05–0.15 บาท/ข้อความ
- **นับตามจำนวนผู้รับ** (push หา 5 คน = 5)
- ข้อความถึง user ที่ block หรือ userId ไม่มีจริง = ไม่นับ

### 6.2 Mapping event → ช่องทาง → ต้นทุน (ใช้เป็น spec ของ dispatcher)
| Event | urgency | ช่องทาง | cost_units |
|---|---|---|---|
| ยืนยันการจอง | normal | liff.sendMessages (เพิ่งกดในแอป) / line_reply | 0 |
| เช็คอินสำเร็จ + เลขคิว | normal | liff.sendMessages (เพิ่งสแกน QR) | 0 |
| ดูตำแหน่งคิว / เวลารอ | low | pull (เปิดแอปเอง ผ่าน Rich Menu) | 0 |
| เตือนล่วงหน้า 1 วัน | low | telegram/pwa ถ้ามี → ไม่งั้น line_push (เปิด/ปิดได้ด้วย reminder_enabled) | 0 หรือ 1 |
| **ใกล้คิว / ถึงคิว** | **critical** | telegram/pwa ฟรีก่อน → ไม่งั้น **line_push** | 0 หรือ 1 |

> หลักการ: จุดที่ยอมจ่ายคือ critical เท่านั้น (คนไข้ไม่ได้จ้องแอป pull ไม่ทัน reply ใช้ไม่ได้) ตัวเลขเป้าหมาย: ~1 paid push ต่อการมา 1 ครั้ง
> **Telegram = ฟรีทุก event (cost_units=0) ไม่มี sync/async split** ต่างจาก LINE → tenant ที่ผูก Telegram (หรือ PWA) ไว้ จะไม่เสียค่า push แม้แต่ event critical; ถ้าอยากต้นทุน 0 ให้ตั้ง `channel_priority` ดัน Telegram/PWA เป็นช่องหลัก แล้วใช้ line_push เป็น fallback เฉพาะคนที่ผูกแต่ LINE

### 6.3 LINE integration
- **Webhook route ต่อ tenant:** `POST /webhooks/line/<tenant>` (Flask)
  - verify `X-Line-Signature` ด้วย channel secret (HMAC) **ก่อน** ประมวลผลทุกครั้ง — reject ถ้าไม่ผ่าน
  - รับ event ตอบด้วย **reply message (ฟรี)** ผ่าน reply token; webhook ที่มี reply token เท่านั้นที่ reply ได้
  - event `follow`/`message` -> ผูก/อัปเดต `channel_links` (line userId)
- **LIFF / LINE MINI App:**
  - ใช้หน้า booking/check-in Jinja2 เดิม + ใส่ LIFF SDK init ที่หัวหน้า
  - ดึง LINE profile (userId, displayName) + **ID token แล้วส่งให้ server verify** (อย่าเชื่อ userId จาก client ดิบ ๆ)
  - **แนวทางปัจจุบัน:** สร้าง LIFF app ใหม่ในรูปแบบ LINE MINI App (LINE กำลังรวม LIFF เข้า LINE MINI App)
  - ยืนยันแบบฟรีด้วย `liff.sendMessages()` ตอน user เพิ่งทำ action (มี caveat: ใช้ไม่ได้ถ้า LIFF ถูก reload จาก recently-used; ต้องเปิดจาก URL ในแชท + ต้องมี scope `chat_message.write`)
  - **Layout caveat (Android, มี.ค. 2026):** edge-to-edge ทำให้ปุ่มล่างทับ navigation bar — ต้องเผื่อ safe-area-inset ด้านล่าง (ปุ่ม "ยืนยันการจอง"/"เช็คอิน")
- **Rich Menu (ฟรี):** เมนูถาวร: จองนัด / เช็คอิน / ดูคิวของฉัน / นัดของฉัน → เปิด LIFF หรือ postback
- **QR check-in:** QR ที่จุดบริการ encode LIFF URL พร้อม `service_point_id` → เปิด → mark check-in → liff.sendMessages ยืนยันเลขคิว (ฟรี)

### 6.4 Telegram integration (parity กับ LINE — อ้างตาราง 6.0)
- **Bot setup ต่อ tenant (BotFather):** สร้าง bot ผ่าน @BotFather ได้ token; ตั้ง **Main Mini App** (Bot Settings → `/newapp`) เพื่อให้มีปุ่ม "Launch app" + screenshots บนโปรไฟล์ bot และปลดล็อกฟีเจอร์ Mini App เต็ม; เก็บ token ใน `messaging_config.telegram_bot_token_enc`
  - **ทางเลือก shared bot:** ใช้ bot กลางตัวเดียวแล้วแยก tenant ด้วย startapp param — friction น้อยกว่า (ไม่ต้องตั้ง BotFather ต่อราย) แต่ brand ไม่แยก; **default ของแผนคือ bot-per-tenant** เพื่อ parity กับ LINE OA — ยืนยันกับเจ้าของถ้าจะเปลี่ยน
  - **เจ้าของ bot รองรับ 2 รูปแบบ: SaaS-managed / tenant BYO token — provisioning ละเอียดใน §6.8 (runtime เหมือนกันทั้งคู่)**
- **Webhook route ต่อ tenant:** `POST /webhooks/telegram/<tenant>`
  - **ลงทะเบียน webhook ด้วย Bot API `setWebhook`** (programmatic ต่อ bot) — ไม่ใช่ตั้งใน console แบบ LINE; ตั้ง secret token ของ webhook ไว้ verify ด้วย
  - ตอบ event ด้วย bot message ได้เลย (**ฟรีเสมอ** ไม่มี reply-token แบบ LINE)
  - event `/start` / message -> ผูก/อัปเดต `channel_links` (telegram chat_id); `/start <param>` ใช้ deep link ได้
- **Telegram Mini App (= LIFF equivalent):** หน้า booking/check-in Jinja2 เดิม + `telegram-web-app.js` ที่ `<head>` + glue
  - **ต้อง validate `initData` ที่ server:** เทียบ `hash` กับ HMAC-SHA256 ของ data-check-string โดย secret key = HMAC-SHA256(bot_token, "WebAppData"); ตรวจ `auth_date` ไม่เกิน ~5 นาที — ใช้ lib Python (`telegram-init-data`) อย่าเขียน HMAC เอง
  - **HTTPS บังคับ** (เปิดบน localhost ไม่ได้; ทดสอบบน test server ใช้ http ได้)
  - มี 6 วิธีเปิด Mini App; ที่ใช้: **Menu Button**, **Direct Link**, inline/keyboard button
- **Menu Button (= Rich Menu equivalent, ฟรี):** ตั้งด้วย Bot API `setChatMenuButton` → ปุ่มถาวรข้างช่องพิมพ์เปิด Mini App; เมนูคำสั่ง `/` ตั้งด้วย `setMyCommands` (จองนัด / เช็คอิน / ดูคิว / นัดของฉัน)
- **QR check-in (= LIFF QR equivalent):**
  - ถ้ามี `telegram_mini_app_short_name`: QR encode **direct Mini App link** `https://t.me/<bot>/<app>?startapp=sp_<service_point_id>` → เปิด Mini App → อ่าน `start_param` (= ค่า startapp) → mark check-in → ส่ง bot message ยืนยันเลขคิว (ฟรี)
  - ถ้าไม่มี short name / ยังไม่ได้ทำ `/newapp`: QR encode **bot deep link fallback** `https://t.me/<bot>?start=sp_<service_point_id>` → webhook รับ `/start sp_<id>` → bot ส่ง inline `web_app` button เปิดหน้า check-in
  - startapp อนุญาตเฉพาะ `A-Z a-z 0-9 _ -` ยาวได้ถึง 512 ตัว; หลายค่าใช้ delimiter เช่น `__` แล้ว split ฝั่ง client; ค่าซับซ้อนแนะนำ base64url
  - **caveat:** Mini App ที่เปิดจาก direct link **ส่งข้อความแทนผู้ใช้ไม่ได้** (ต่างจาก keyboard button) — แต่ไม่เป็นปัญหาเพราะ backend ส่ง bot message ฟรีอยู่แล้ว (ไม่ต้องพึ่ง trick แบบ liff.sendMessages)
- **ยืนยัน/แจ้งเตือน (ฟรีเสมอ):** ส่ง bot message ปกติผ่าน dispatcher — ทุก event `cost_units=0`; เป็นช่อง async ฟรีที่ดัน**ก่อน** line_push สำหรับ critical
- ผูก `channel_links` ด้วย Telegram chat_id

### 6.5 PWA
- เพิ่มแบบ additive บน web app เดิม: `manifest.json` (installable), service worker (cache shell + รับ push), HTTPS
- **Web Push (VAPID):** เก็บ subscription ใน `channel_links.raw_profile`; เก็บ VAPID ต่อ tenant ที่ `messaging_config.pwa_vapid_public_key` + `pwa_vapid_private_key_enc` (private key ต้อง encrypt); ช่อง async ฟรี
  - **Tradeoff per-tenant vs global VAPID (ตัดสินใจ):** per-tenant (ตามแผน) ให้ tenant isolation/white-label แต่ต้อง gen + encrypt + จัดการ N private key; ถ้าเน้น simplicity ใช้ **global VAPID keypair ระดับ platform** (env เดียว) ง่ายกว่าและเป็น pattern มาตรฐาน (VAPID ไม่โชว์ต่อ user จึงไม่กระทบ brand) — **แผนคง per-tenant ไว้เพื่อรองรับ white-label**; ถ้าไม่ต้องการ isolation ระดับนั้น สลับเป็น global ได้โดยไม่กระทบ flow
- **Caveat ที่ต้องบอก user:** iOS Safari รองรับ PWA push แบบจำกัด + ต้อง Add to Home Screen + ขออนุญาตเอง อัตรา opt-in ต่ำ → อย่าพึ่ง PWA เป็นช่องหลัก (สำหรับไทย LINE คือช่องหลัก)
- **ห้ามใช้ localStorage/sessionStorage ใน artifact/sandbox** — แต่ใน production PWA จริงใช้ได้ตามปกติ

### 6.6 จอแสดงคิว (Queue display)
- `GET /queue/display/<service_point_id>` — Jinja2 page สำหรับเปิดบน TV/จอที่คลินิก
- แสดง "กำลังเรียกหมายเลข X" + คิวที่รอ
- auto-refresh: ใช้ **SSE** หรือ polling ทุก 3–5 วิ (display ล้วน — JS น้อยสุด ยอมรับได้)
- ไม่ต้องซื้อ hardware: จอ + browser พอ

### 6.7 หน้า web เดียวเสิร์ฟทั้ง LINE / Telegram / PWA (context detection)
หน้า booking/check-in เป็น Jinja2 ตัวเดียวกัน — ต่างกันแค่ SDK glue ที่หัวหน้า ให้ detect context แล้วโหลด SDK ที่ถูก (logic ตัดสินใจยังอยู่ Python ฝั่ง server, JS ส่วนนี้เป็นแค่ adapter)

ลำดับการ detect (ฝั่ง client เล็กน้อย):
1. ถ้ามี `window.Telegram?.WebApp?.initData` (ไม่ว่าง) → **Telegram Mini App** → ส่ง initData ให้ server validate
2. else ถ้า LIFF SDK init แล้ว `liff.isInClient()` เป็น true → **LINE LIFF/MINI App** → ส่ง ID token ให้ server verify
3. else → **เว็บปกติ / PWA** → ใช้ flow ผูกตัวตนแบบปกติ (เช่น เบอร์/ลิงก์ยืนยัน)

- **server เป็นคนตัดสิน channel จริงเสมอ** (จากผลการ verify ที่ผ่าน) ไม่ใช่เชื่อค่า client บอก
- เก็บ channel ที่ detect ได้ลง `channel_links` (line / telegram / pwa)
- ปุ่ม submit/ยืนยัน: เผื่อ safe-area ด้านล่าง (LINE Android edge-to-edge) และเรียก SDK ที่ตรง context

**Gotchas (จุดบั๊กเงียบ — ระวัง):**
- ต้อง `await liff.init()` ให้เสร็จ**ก่อน** เรียก `liff.isInClient()` ไม่งั้นค่าไม่น่าเชื่อถือ
- โหลด SDK **ตาม context ที่ detect ได้** อย่าโหลด LIFF SDK กับ Telegram SDK พร้อมกันทุกครั้ง (กัน conflict/เปลือง)
- `Telegram.WebApp.initData` **อาจว่างได้แม้เปิดใน Telegram** (บาง launch mode เช่น direct link) → ใช้ว่าง/ไม่ว่างเป็นสัญญาณอย่างเดียวไม่พอ ให้ **server validate เป็นตัวตัดสิน**
- detect ไม่ออกทั้งคู่ → **fallback เป็น flow เว็บปกติ ไม่ใช่ error**

### 6.8 Tenant provisioning / onboarding checklist (LINE + Telegram)

> **หลักการ:** ขั้นตอน "สมัคร account / สร้าง bot / ตั้งใน console" เป็นงาน manual ครั้งเดียวต่อ tenant; ส่วนที่ทำผ่าน API ได้ ให้ระบบ automate. **Runtime (webhook / ส่งข้อความ / Mini App / validate) อ่านค่าจาก `messaging_config` เหมือนกันทุกกรณี** — รูปแบบเจ้าของ account กระทบแค่ provisioning + lifecycle ไม่กระทบ hot path

#### LINE (ต่อ tenant) — รายละเอียด account ดู §6.3
1. LINE **Business ID** (login/เจ้าของ)
2. **Provider** (แนะนำแยกต่อ tenant)
3. **LINE Official Account** (คนไข้แอดเป็นเพื่อน)
4. **Messaging API channel** (ผูกกับ OA) → `line_channel_id`, `line_channel_secret_enc`, `line_channel_token_enc`
5. **LINE Login channel** (host LIFF) → `line_login_channel_id`
6. **LIFF app** ใต้ Login channel → `line_liff_id`; ตั้ง "Linked bots" = Messaging API channel
7. (optional) อัปเกรดเป็น **LINE MINI App** (ต้อง review)

> **กฎเหล็ก LINE:** Messaging API channel กับ LINE Login channel ของ tenant เดียวกัน **ต้องอยู่ provider เดียวกัน** ไม่งั้น userId จาก LIFF ≠ userId จาก webhook → `channel_links` map ผิด

#### Telegram (ต่อ tenant) — รองรับ 2 รูปแบบเจ้าของ bot
**ทั้งสองรูปแบบจบที่เดียวกัน: token (+ webhook secret) อยู่ใน `messaging_config` → runtime เหมือนกัน** ต่างแค่ "ใครสร้าง bot / ใครถือ Telegram account" (`telegram_bot_ownership`)

**รูปแบบ A — SaaS-managed (`telegram_bot_ownership='saas'`):**
1. SaaS ops สร้าง bot ใน **Telegram account ของ SaaS** (`/newbot`) → token
2. ตั้ง brand (`/setname` ฯลฯ) + (ถ้าต้องการ direct-link Mini App) `/newapp` ตั้ง short name + Web App URL
3. ใส่ token ในหน้า config ของ tenant (ownership=`saas`) → ระบบรัน provisioning helper อัตโนมัติ
4. **Ops note (ลิมิต ~20 bot/Telegram account):** SaaS ต้องมี **pool ของ Telegram account** + registry ใน control/`public` schema (ดู §4.11 — `saas_telegram_accounts` + `saas_telegram_bots`) map bot → account → tenant; onboard เรียก `telegram_pool.allocate_account()` เลือก account ว่างก่อนสร้าง bot แล้ว `register_bot()` หลังสร้างเสร็จ; pool เต็ม → เพิ่ม account ใหม่ (token จริงยังอยู่ที่ tenant `messaging_config` ไม่ซ้ำใน registry)

**รูปแบบ B — Tenant BYO bot (`telegram_bot_ownership='tenant'`):**
1. โรงพยาบาลสร้าง bot ใน **account ของตัวเอง** (`/newbot`) → token
2. (ถ้าต้องการ direct-link Mini App) ทำ `/newapp` + brand เองตามคู่มือ — **เฉพาะเจ้าของ bot ทำได้** (SaaS ทำแทนไม่ได้เพราะอยู่คนละ account)
3. โรงพยาบาล **วาง token ในหน้า admin ของ SaaS** → ระบบ validate (`getMe`) + รัน provisioning helper อัตโนมัติ
4. โรงพยาบาลเป็นเจ้าของ ควบคุม/revoke token เองได้; ถ้าจะให้ SaaS จัดการเต็ม ใช้ BotFather "Transfer Ownership" โอน bot ไป account SaaS (กลายเป็นรูปแบบ A)

**Provisioning helper (Python, Flask-first) — ใช้ได้ทั้ง A และ B (token-driven):**
ไฟล์เสนอ: `flask_app/app/services/telegram_provisioning.py`
```python
def provision_telegram_bot(tenant, token: str, ownership: str,
                           mini_app_short_name: str | None = None) -> dict:
    """
    ใช้ได้ทั้ง ownership='saas' และ 'tenant' (ต่างแค่ใครส่ง token เข้ามา):
    1. getMe(token)            -> verify token ใช้ได้ + ดึง username -> เก็บ telegram_bot_username
    2. gen webhook secret      -> เก็บ telegram_webhook_secret_enc
    3. setWebhook(url=/webhooks/telegram/<tenant>, secret_token=secret, allowed_updates=[...])
    4. setChatMenuButton(web_app = Mini App หรือ booking URL)   # ทำได้ด้วย token ไม่ต้อง /newapp
    5. setMyCommands([...])
    6. เก็บ token (encrypt), ownership, short_name ลง messaging_config + ตั้ง `telegram_status='active'`, เคลียร์ `telegram_last_error`
    คืน status; ใช้ตอน onboard ครั้งแรก และตอน re-provision (token เปลี่ยน) — idempotent
    """
```
- **`/newapp` ทำผ่าน Bot API ไม่ได้** — เป็นงาน BotFather manual ของเจ้าของ bot (A=SaaS, B=โรงพยาบาล); ส่วน `getMe`/`setWebhook`/`setChatMenuButton`/`setMyCommands` ทำผ่าน token ได้หมด → **helper เดียวใช้ได้ทั้งสอง model**
- **QR check-in fallback (ถ้าไม่มี Mini App registered / `telegram_mini_app_short_name`=null):** ใช้ bot deep link `t.me/<bot>?start=sp_<id>` แทน direct link → เปิดแชท bot → bot ตอบด้วย inline button (web_app) เปิด Mini App (ต้องการแค่ token ไม่ต้อง `/newapp`)

**Lifecycle (ทั้งสอง model):**
- token ใช้ไม่ได้ (B: โรงพยาบาล revoke เอง / A: rotate) → webhook/ส่งข้อความ fail 401 → ตั้ง `telegram_status='error'` + `telegram_last_error`, dispatcher ถือว่า Telegram unavailable และ fallback ช่องถัดไป, แจ้ง tenant → เรียก `provision_telegram_bot` ใหม่ด้วย token ใหม่
- re-provision ใช้ helper เดิม (setWebhook/menu/commands เซ็ตทับได้)

---

## 7. แผนเป็น Phase (ลำดับการทำ + acceptance criteria)

> ทำตามลำดับ dependency. แต่ละ task: ระบุ files, แล้วต้องผ่าน acceptance criteria ก่อนถือว่าเสร็จ
> **ก่อนแตะ FastAPI ทุก task: ทบทวนกฎ 0.2 (SET search_path)**

### Phase 0 — Foundation (ทุกอย่างพึ่งอันนี้)
| Task | รายละเอียด | Acceptance |
|---|---|---|
| 0.1 | สร้างตาราง 4.1–4.10 บน `tenant_humnoi` | `\dt` เห็นครบทุกตาราง, FK ถูกต้อง |
| 0.2 | seed `service_points`, `sessions`, `queue_policy`, `grace_policy` (default rows) | query เห็นข้อมูลตัวอย่าง |
| 0.3 | ALTER `appointments` เพิ่ม column (4.3) + ตรวจ existing ก่อน | `\d appointments` เห็น column ใหม่, ของเดิมไม่พัง |
| 0.4 | ใส่ encryption helper (5.7 — Fernet/MultiFernet) สำหรับ `*_enc` columns + ตั้ง env `MESSAGING_ENCRYPTION_KEYS` | encrypt/decrypt token ได้ค่าเดิม, ไม่มี plaintext ใน DB/log, รองรับ rotation |
| 0.5 | SQLAlchemy models ใน `models.py` สำหรับตารางใหม่ | import ได้ ไม่มี error |

### Phase 1 — Queue core + check-in
| Task | รายละเอียด | Files | Acceptance |
|---|---|---|---|
| 1.1 | `queue_service.transition()` (5.1) + เขียน queue_events ทุกครั้ง | `services/queue_service.py` | unit test: ทุก transition มี event row + timestamp ถูก field |
| 1.2 | `check_in()` (5.2) + queue_number atomic | `services/queue_service.py` | สแกนพร้อมกัน 2 ครั้งไม่ได้เลขซ้ำ (concurrency test) |
| 1.3 | หน้า check-in (LIFF/web) + QR เปิดพร้อม service_point_id | `templates/queue/checkin.html`, `queue_routes.py` | เปิด URL พร้อม param แล้ว check-in สำเร็จ, ได้เลขคิว |
| 1.4 | staff console: ปุ่ม "เรียกคิวถัดไป" / start / done / skip | `templates/queue/console.html`, `queue_routes.py` | กดแล้วสถานะเปลี่ยน + event ถูกบันทึก |
| 1.5 | จอแสดงคิว + auto-refresh (6.6) | `templates/queue/display.html` | แสดงเลขที่กำลังเรียก, refresh เห็นการเปลี่ยน |
| 1.6 | FastAPI endpoints อ่าน/เขียน queue (ตามต้องการ) | `fastapi_app/app/queue.py` | **ทุก endpoint มี SET search_path**, ไม่มี UndefinedTable |

### Phase 1B — Session generator (ทำหลัง Phase 1, ขนานกับ Phase 2-3 ได้)
> queue core (Phase 1) ทำงานกับ session ที่ seed manual ได้แล้ว — phase นี้ทำให้ session มาจาก availability เดิมอัตโนมัติ
> **มี prerequisite design decision** (ดู 5.8) — ต้องเคลียร์ service_point ↔ template mapping ก่อนเริ่ม code

| Task | รายละเอียด | Files | Acceptance |
|---|---|---|---|
| 1B.0 | ตรวจ schema `availabilities`/`date_overrides` จริง + ตัดสินใจ mapping service_point↔template (`service_points.availability_template_id`) | `models.py`, migration | ทำแล้ว: mapping ชัดเจน + migration/model/test มีแล้ว |
| 1B.1 | `session_service.generate_sessions()` (5.8) idempotent UPSERT | `services/session_service.py` | รัน 2 ครั้งไม่เกิด session ซ้ำ; date_override ทับถูกต้อง |
| 1B.2 | `sync_sessions_rolling()` + scheduler รายวัน | `services/session_service.py` + scheduler | sessions ช่วง 14 วันข้างหน้าถูกสร้างครบทุก active service_point |
| 1B.3 | trigger re-sync ตอน save availability/override | ~~`availability_routes.py`~~ → **`fastapi_app/app/availability.py`** (A3: flask `availability_routes.py` เป็นแค่ proxy ที่ `make_api_request` ไป FastAPI — persist จริงที่ FastAPI; trigger จึงวางที่ FastAPI endpoint หลัง commit, enqueue งานผ่าน RQ ไป `session_service.resync_template_sessions_job` — ดู `fastapi_app/app/session_resync.py`) | แก้ availability → session อนาคต update, อดีตไม่แตะ |
| 1B.4 | guard: ห้ามแก้ session ที่มี queue_entries | `services/session_service.py` | test: session ที่มีคิวแล้ว ไม่ถูกแก้/ลบ |

### Phase 2 — Priority + grace
| Task | รายละเอียด | Files | Acceptance |
|---|---|---|---|
| 2.1 | `grace_service.classify_on_checkin()` (5.3) | `services/grace_service.py` | unit test ครบ 4 เคส (in-window / same-session-late / cross-session / no-show) |
| 2.2 | ผูก grace เข้ากับ check_in() + เขียน reclass event | `services/queue_service.py` | นัดมาบ่ายที่จองเช้า → entry_class='walkin' + event 'reclass' |
| 2.3 | `priority_service.call_next()` mode='ratio' + starvation guard (5.4) | `services/priority_service.py` | test: เรียกนัด 3 แล้วแทรก walk-in 1; walk-in รอเกิน threshold ถูกดันขึ้น |
| 2.4 | `compute_priority_score()` mode='score' | `services/priority_service.py` | test: appointment ใน window ชนะ walk-in; walk-in รอนานมากชนะในที่สุด |
| 2.5 | No-show sweeper + **(D) stale `called` timeout** (background/cron ต่อ tenant; + preflight ใน call_next) | `services/queue_service.py` + scheduler | entry checked_in เลยเวลาปิด → no_show + event; entry called เกิน `call_timeout_min` → no_show/skipped + event + คืน capacity |

### Phase 3 — Wait estimation
| Task | รายละเอียด | Files | Acceptance |
|---|---|---|---|
| 3.1 | `WaitEstimator` protocol + `EstimateResult` + factory (5.5) | `services/estimation/base.py` | factory คืน SimpleAverageEstimator |
| 3.2 | `SimpleAverageEstimator` (level 1-2, p80, หาร servers) | `services/estimation/simple_avg.py` | test: ข้อมูล mock → wait สมเหตุผล |
| 3.3 | แสดง estimate บนหน้า "ดูคิวของฉัน" (pull) | `templates/queue/my_queue.html` | เปิดแล้วเห็น "เหลือ N คิว ~M นาที" |
| 3.4 | ทุกการเรียก wait ผ่าน `get_estimator()` เท่านั้น | (ทั้งระบบ) | grep ไม่เจอการคำนวณ wait แบบ inline ที่อื่น |

### Phase 4 — Channels + notification dispatcher
> ทำ **LINE และ Telegram ให้ครบทั้งคู่** (ดูตาราง parity 6.0) — แต่ละช่องมีชุด task คู่ขนานกัน
> **ลำดับที่ล็อก (สำคัญ):** ก่อนแตะ Phase 4.0/4.13 ต้องทำ **(D) called-timeout** (Phase 2.5) และ **(A) identity resolution contract** (§4.6.1 — canonical `patient_ref` + กลไกผูก `channel_links`) ให้เสร็จก่อน เพราะ dispatcher (4.1) และ queue notification wiring (4.13) พึ่งทั้งสองอย่างโดยตรง — ถ้า identity ยังไม่ลง push จะไม่มีผู้รับ, ถ้า called ไม่ timeout capacity จะรั่ว

**Dispatcher (แกนกลาง):**
| Task | รายละเอียด | Files | Acceptance |
|---|---|---|---|
| 4.0 | Messaging config prep (§4.7): migration เพิ่ม `line_login_channel_id`, channel status/error fields, Telegram webhook secret/ownership/short name, PWA VAPID fields; update SQLAlchemy model + legacy SQL + admin settings UI + tests | `migrations/...`, `shared_db/models.py`, settings/admin templates | ทุก tenant มี columns ใหม่; `*_enc` encrypt/decrypt ได้; dispatcher ใช้เฉพาะ channel `status='active'`; ไม่มี plaintext secret ใน DB/log |
| 4.1 | `notify_service.notify()` (5.6) + เลือกช่องตาม 6.2 + log + advisory-lock dedupe | `services/notify_service.py` | test: telegram → cost_units=0 ทุก event; LINE async critical → cost_units=1; concurrent notify event เดียวกันส่งจริงครั้งเดียว |

**LINE:**
| Task | รายละเอียด | Files | Acceptance |
|---|---|---|---|
| 4.2 | LINE webhook + signature verify + reply (ฟรี) + channel_links | `webhook_routes.py` | signature ผิด → reject; follow event → channel_link ถูกสร้าง |
| 4.3 | LIFF init + ID token verify (server) + safe-area | booking/checkin templates | client ส่ง ID token → server verify ผ่าน → userId เชื่อถือได้ |
| 4.4 | Rich Menu setup (ฟรี) | script/admin | เมนูปรากฏในแชท, ปุ่มเปิด LIFF ได้ |
| 4.5 | LINE QR check-in (LIFF URL + `service_point_id`) | templates | สแกน → check-in → `liff.sendMessages` ยืนยันเลขคิว (ฟรี) |

**Telegram (parity เท่า LINE):**
| Task | รายละเอียด | Files | Acceptance |
|---|---|---|---|
| 4.6 | Telegram provisioning helper (§6.8) — getMe/setWebhook(+secret)/setChatMenuButton/setMyCommands รองรับ ownership `saas`+`tenant`; + หน้า admin ให้ tenant วาง token (BYO); + channel_links | `services/telegram_provisioning.py`, `webhook_routes.py`, admin template | provision ด้วย token → webhook ลงทะเบียน + verify secret ได้; `/start` → channel_link; token invalid → re-provision ได้ |
| 4.6b | (Model A เท่านั้น) Control-plane account pool (§4.11) — `saas_telegram_accounts` + `saas_telegram_bots` + `telegram_pool.allocate_account()`/`register_bot()` | `public` migration, `services/telegram_pool.py` | allocate คืน account ว่าง; pool เต็ม → raise; register บันทึก allocation; token ไม่ถูกเก็บซ้ำใน registry |
| 4.7 | Telegram webhook + **initData validate ที่ server** (HMAC + auth_date) | `webhook_routes.py`, `fastapi_app/app/...` | initData ปลอม → reject; auth_date เก่า → reject |
| 4.8 | Telegram Mini App init (`telegram-web-app.js`) + glue | booking/checkin templates | เปิดใน Telegram → validate ผ่าน → chat_id เชื่อถือได้ |
| 4.9 | Telegram Menu Button (`setChatMenuButton`) + `setMyCommands` (= Rich Menu) | script/admin | ปุ่ม/เมนูปรากฏ เปิด Mini App ได้ |
| 4.10 | Telegram QR check-in: direct Mini App `?startapp=sp_<id>` เมื่อมี short name; fallback `?start=sp_<id>` + inline `web_app` button เมื่อไม่มี `/newapp` | templates, `webhook_routes.py` | ทั้ง direct และ fallback สแกน → check-in → bot message ยืนยัน (ฟรี); ไม่พึ่ง client ส่งข้อความเอง |

**ร่วมทุก channel:**
| Task | รายละเอียด | Files | Acceptance |
|---|---|---|---|
| 4.11 | PWA: manifest + service worker + Web Push (VAPID per tenant) | `static/`, `templates/`, `messaging_config` | ติดตั้ง PWA ได้, subscription ถูกเก็บใน `channel_links.raw_profile`, VAPID private key encrypt, รับ push ได้ (ทดสอบ Android/Chrome) |
| 4.12 | Context detection หน้า web เดียว (6.7) — LINE/Telegram/เว็บ | booking/checkin templates | เปิดในแต่ละ context → detect + verify ถูก channel, server เป็นคนตัดสิน |
| 4.13 | ผูก dispatcher เข้ากับ event คิว: checkin_confirm, queue_near, queue_turn | `services/queue_service.py` | call_next → queue_turn ไปคนถูกคน + ช่องถูก (LINE/Telegram/PWA), log ครบ |

### Phase 5 — Analytics dashboard (ทำหลังมีข้อมูลจริงพอ)
| Task | รายละเอียด | Files | Acceptance |
|---|---|---|---|
| 5.1 | SQL aggregation: avg wait/ชม., throughput, no-show rate, peak | `services/analytics_service.py` | query คืนค่าถูกต้องเทียบ manual |
| 5.2 | หน้า dashboard Jinja2 + Chart.js (กราฟเท่านั้น) | `templates/analytics/index.html` | แสดงกราฟ, logic อยู่ Python ทั้งหมด |
| 5.3 | รายงานต้นทุนข้อความจาก notification_log + LINE quota API | `services/analytics_service.py` | แสดงยอดข้อความใช้/เหลือ ต่อ tenant |

**นิยาม metric ที่ล็อกแล้ว (15 มิ.ย. 2026):**
- `no_show_rate = no_show / (done + no_show)` — denominator ใช้เฉพาะ terminal outcomes; active statuses (`checked_in`, `called`, `in_service`) ไม่ถูกนำมาหาร
- cost report ต้องแยก **sent cost** (`SUM(cost_units) WHERE status='sent'`) ออกจาก **attempted/failed cost** เพื่อไม่ตีความ failed LINE push ว่าเสียเงินจริง
- `total_entries` ยังรายงานทั้งหมดได้ แต่ต้องแสดง/เก็บ `terminal_entries` เพื่อ audit denominator

---

## 8. Future hooks (สร้างไว้แล้ว ไม่ต้อง implement intelligence ตอนนี้)

ออกแบบ seam เหล่านี้ในแผนข้างบนแล้ว — เป้าหมายคือ **ใส่ความฉลาดทีหลังได้โดยไม่ต้อง migrate เจ็บตัว**

1. **`estimate_wait()` strategy** (5.5) → สลับเป็น Erlang-C (level 3) / ML (level 4) ได้โดยไม่แตะ caller
2. **Service-point / parallel_servers** → รองรับการคำนวณแบบหลายช่องบริการ + analytics ราย resource
3. **Rich visit record** (`appointment_type`, `patient_category`, doctor, slot, arrival deltas) → กลายเป็น ML feature + มิติ analytics
4. **No-show capture พร้อม context** → future no-show prediction / overbooking
5. **`queue_events` append-only** → ขับ analytics + ML training ได้ "ฟรี" ทีหลัง
6. **`notification_log`** → cost analytics + กันแจ้งซ้ำ + hook สำหรับ smart notification timing
7. **Config tables** (`queue_policy`, `grace_policy`, `messaging_config`) → เพิ่ม/แก้นโยบาย = แก้ config ไม่ใช่แก้ code
8. **Session generator** (5.8 + Phase 1B) → materialize sessions จาก availability template + date_overrides (+ TeamUp ภายหลัง), idempotent, รักษา history

---

## 9. Testing & Verification

### 9.1 Database
```bash
# เชื่อม DB + ตั้ง schema ก่อน query เสมอ
psql -d nuddee
SET search_path TO tenant_humnoi;
\dt                      # ดูตารางครบไหม
\d queue_entries         # ตรวจ columns
```

### 9.2 Unit tests (สำคัญ — logic อยู่ Python)
- `grace_service.classify_on_checkin` — ครบ 4 เคส
- `priority_service` — ratio interleaving + starvation + score ordering
- `SimpleAverageEstimator` — ค่า wait สมเหตุผลกับ mock data
- `notify_service` — เลือกช่องถูก + cost_units ถูก + fallback
- `queue_service.transition` — มี queue_events ทุก transition + timestamp ถูก field
- check-in concurrency — queue_number ไม่ซ้ำ

### 9.3 FastAPI regression check
- ทุก endpoint ใหม่: ยืนยันเรียก `bind_tenant(db, schema)` + `SET search_path` ที่ต้นฟังก์ชัน **โดยไม่ commit ทันทีหลัง SET** (commit ที่ท้ายงานถ้าเป็น write — ดูกฎ 0.2). ห้าม SET manual อย่างเดียวโดยไม่ bind (commit แล้ว query ต่อจะพัง)
- ยืนยันใช้ `Depends(get_db)` ไม่ใช่ `Depends(get_tenant_db)` factory เดิม และ resolve schema จาก `public.hospitals.schema_name` (ไม่ hardcode `tenant_{subdomain}` เพราะ subdomain มี hyphen ได้)
- ทดสอบ subdomain `humnoi.localhost` → ไม่ append `?subdomain=` ผิด

### 9.4 Integration (manual)
- จองช่วงเวลา → สแกน QR check-in → ได้เลขคิว (liff.sendMessages ฟรี) → staff เรียกคิว → คนไข้ได้ push "ถึงคิว"
- ทดสอบ grace: จองเช้า เช็คอินบ่าย → ถูก demote เป็น walk-in
- ทดสอบ webhook signature/initData ปลอม → ถูก reject

### 9.5 Cost verification
- หลัง flow ครบ 1 รอบ: query `notification_log` → ยืนยันมี paid push (cost_units=1) แค่ event critical, ที่เหลือ cost_units=0

---

## 10. สิ่งที่ "ห้ามทำ" (สรุปกันพลาด)

- ห้ามผลัก business logic ไป JavaScript (ยกเว้น SDK glue + display)
- ห้าม FastAPI endpoint ที่ไม่ `bind_tenant` + SET search_path → จะเกิด UndefinedTable (และ commit แล้ว query ต่อจะพังเพราะ unbound session ถูกบังคับ public)
- ห้ามใช้ `Depends(get_tenant_db)` factory เดิม (ใช้ `Depends(get_db)` + `bind_tenant(db, schema)`)
- ห้ามเก็บ token/secret เป็น plaintext
- ห้ามคำนวณ wait time แบบ inline นอก `get_estimator()`
- ห้าม assign queue_number แบบ `MAX()+1` non-atomic (race condition)
- ห้าม update/delete `queue_events` (append-only)
- ห้ามพยายามเรียก "free LINE reply/liff.sendMessages" จาก background job (เป็นไปไม่ได้ — async LINE มีแต่ paid push)
- (H) ห้ามส่ง `queue_turn`/`queue_near` push แบบ sync ใน request ของ staff console — ต้อง enqueue ผ่าน worker/RQ (worker ต้องโหลด `MESSAGING_ENCRYPTION_KEYS`)
- (A) ห้าม push ไป patient ที่ยังไม่มี `patient_ref` ยืนยันตัวตน + `channel_links` active (ดู §4.6.1) — ให้ pull/log แทน; ห้ามใช้ชื่อเป็น `patient_ref`
- (D) ห้ามปล่อย entry สถานะ `called` ค้างโดยไม่มี timeout (capacity รั่ว) — sweeper/preflight ต้องปิด stale called ตาม `call_timeout_min`
- (G) ห้ามเทียบ session `TIME` กับ `now` โดยไม่ตรึง timezone ของ tenant (default `Asia/Bangkok`) — grace จะเลื่อน
- (E) ห้ามสร้าง "sequence ต่อ (service_point, date)" สำหรับ queue_number (ใช้ counter table หรือ advisory lock + `MAX()+1`)
- ห้าม hardcode `?subdomain=` ใน URL (ใช้ `url_helper.py`)
- ห้ามเรียก MCP server URL ผ่าน fetch() ใน static HTML artifact

---

## 11. Glossary

| คำ | ความหมาย |
|---|---|
| tenant | โรงพยาบาลหนึ่งราย = หนึ่ง PostgreSQL schema (เช่น `tenant_humnoi`) |
| service_point | จุดบริการ (ห้อง/เคาน์เตอร์/หมอ) ที่คิวแยกกัน |
| session | ช่วงเวลาบริการต่อจุดบริการต่อวัน (เช่น "เช้า") |
| queue_entry | รายการในคิว (ผูก appointment หรือเป็น walk-in) |
| entry_class | คลาส effective ของคิว: appointment \| walkin (อาจถูก demote โดย grace) |
| slot_type | exact (นัดเวลาตรง) \| window (นัดช่วงแล้วจับคิวหน้างาน) |
| LIFF | LINE Front-end Framework — web app รันใน LINE (กำลังรวมเป็น LINE MINI App) |
| reply token | token จาก LINE webhook สำหรับตอบฟรี (ครั้งเดียว, หมดอายุเร็ว) |
| initData | ข้อมูล signed จาก Telegram Mini App ที่ต้อง validate ที่ server |
| pull-based | ผู้ใช้เปิดแอปดูสถานะเอง (ไม่มีค่าใช้จ่าย) |

---

## 12. Decisions Log (พบตอน implement Phase 0–1B, ตัดสินกับเจ้าของ 13 มิ.ย. 2026)

> เกิดจาก audit แผนเทียบ codebase จริง — A1 + A2 **ตัดสินครบแล้ว** (รวม sub-decision ของ A1:
> "นัดนี้ต้องเข้าคิวไหม" กำหนดที่ระดับ `event_type` — ดู A1)

### A1 — slot window ของ grace/priority + "นัด 1:1 ไม่ต้องจับคิว" — ✅ ตัดสินครบแล้ว
**ปัญหา:** §5.3/§5.4 อ้าง `appointment.slot_start` / `slot_end` ที่ **ไม่มีในตาราง** `appointments`
(มีจริง: `start_time`, `end_time` แบบ DateTime, `slot_type`, `session_id`)
**บริบท:** ระบบจองเป็น **exact** โดยธรรมชาติ — slot generate จาก availability × `event_type.duration_minutes`
(booking.py `generate_time_slots`); ทุกนัดมีเวลาเป๊ะ. DB default `slot_type='exact'`; **ยังไม่มีโค้ดเซ็ต
`'window'`** (window booking ยังไม่ถูกสร้าง). `check_in()` เป็น **opt-in** — สร้าง queue_entry เฉพาะตอนมี
คน check-in จริง; `session_id` nullable

**ตัดสิน — คิวเป็น opt-in, มี 3 กรณีอยู่ร่วมกัน:**
- **นัด 1:1 ตามเวลา (exact, ไม่เข้าคิว):** มาตามเวลา → พบเลย, ไม่ check-in, `session_id` null, ไม่มีเลขคิว/grace
  — รองรับอยู่แล้ว (ไม่มีอะไรบังคับให้จับบัตร) ← การจองเฉพาะ 1:1
- **นัดแบบจับคิว (window / exact ที่เลือกเข้าคิว) + walk-in:** check-in → queue_number → grace/priority
**grace/priority (Phase 2) ใช้กับ "ผู้เข้าคิว" เท่านั้น** (นัดที่ check-in + walk-in) — slot window สำหรับ
grace = เวลาของ **session ที่ผูก** (window) หรือ `start_time`/`end_time` (ถ้านัด exact เลือกเข้าคิว).
session = "ช่องคิวของจุดบริการต่อวัน" (ไม่ใช่เวลานัด) — generator สร้างไว้เป็น container ของคิว ไม่บังคับนัดให้ผูก

**✅ sub-decision — ตัดสินแล้ว (14 มิ.ย. 2026): "นัดนี้ต้องเข้าคิวไหม" กำหนดที่ระดับ `event_type`**
ผู้ให้บริการ/สถานบริการเป็นผู้ตั้ง — เพราะการจอง = availability × `event_type` อยู่แล้ว ตัว "บริการ" จึงเป็น
ที่ที่ธรรมชาติที่สุดในการระบุว่าใช้คิวหรือไม่ (ไม่เลือก service_point/appointment)

**โมเดล:** เพิ่ม flag ที่ `event_types` (เสนอชื่อ `requires_queue BOOLEAN` ตั้งในหน้า event-type create/edit):
- `requires_queue = False` → **1:1 ตามเวลา**: จอง = นัดเวลาเป๊ะ; ไม่ออกเลขคิว ไม่ผูก session ไม่เข้า
  grace/priority. check-in (ถ้ามี) = แค่บันทึกการมาถึง
- `requires_queue = True` → **ใช้คิว**: นัดของบริการนี้ + walk-in ที่จุดบริการ → check-in ออก `queue_number`,
  ผูก session, เข้ากฎ grace/priority ตามเงื่อนไข
→ flag นี้คือ "gate" เดียวที่ตัดสินว่า booking/check-in **ออกเลขคิว** หรือ **แค่บันทึกการมาถึง**

**ความสัมพันธ์กับ `slot_type`:** `slot_type` (exact|window) = granularity ของการจอง (เวลาเป๊ะ vs ช่วง);
`requires_queue` = master switch ว่าบริการเข้าคิวไหม. `requires_queue=False` → ไม่มี session/คิว ไม่ว่า slot_type ใด

**default (เลือกตอน implement):** แนะนำ default `False` เพื่อ backward-compat กับพฤติกรรมนัดเดิม แล้วให้
facility opt-in เปิดคิวต่อบริการที่ต้องการ (หรือ default ตาม policy ของ tenant ก็ได้)

**สถานะ implementation (ทำแล้ว 14 มิ.ย. 2026):**
- migration `migrations/add_event_types_requires_queue.py` เพิ่ม/backfill/default/NOT NULL `event_types.requires_queue`
- `shared_db.models.EventType`, FastAPI event_types create/update/response และ booking response expose field นี้แล้ว
- UI settings/event-types มี toggle แล้ว
- check-in: `requires_queue=False` บันทึกการมาถึงอย่างเดียว ไม่สร้าง `queue_entry`/`queue_events`; `requires_queue=True` ใช้ queue path เดิม
- tests ครอบทั้ง requires_queue True/False แล้ว
- grace/priority/session + การออกเลขคิวทำงานเฉพาะ event_type ที่ `requires_queue=True` (event_type ที่ False = ข้ามคิวทั้งหมด)

### A2 — date_override "วันทำงานพิเศษ" เปิด/ปิดได้จริงไหม — ✅ ตัดสินแล้ว (replace)
**สถานะจริง (แก้ความเข้าใจผิดเดิม):** booking engine **REPLACE** ไม่ใช่ clamp — [booking.py:628-633](../fastapi_app/app/booking.py)
ทำ `base_slots = generate_time_slots(custom_start, custom_end, duration)` แทนตารางปกติของวันนั้นทั้งหมด
(และ `if not base_slots` เช็คหลัง replace) → **เปิดวันที่ปกติปิดได้จริง** สร้างผ่านหน้า settings/availability
(ฟอร์มวันพิเศษ: override_type='custom' = เปิดเวลาพิเศษ / 'unavailable' = ปิด)
**ตัดสิน: generator ทำ REPLACE ตรงกับ booking** (แก้แล้ว `session_service._desired_blocks_for_date`):
override.is_unavailable → ไม่มี session; override custom hours → session = ช่วง custom (แทนทั้งวัน, เปิดวันพิเศษได้);
ไม่มี override → weekly. trigger ผ่าน RQ (1B.3) ตอน save → generator สร้าง session ของวันพิเศษอัตโนมัติ
**(แก้ bug)** generator เดิมทำ clamp/intersect → ไม่ตรง booking (วันพิเศษจะไม่มี session) — แก้เป็น replace แล้ว

---

### Patch 15 มิ.ย. 2026 (review รอบ 2 — ก่อนเริ่ม Phase 4.0/4.13)
จาก audit แผนเทียบ notification/queue invariants — patch ก่อน wiring notification:
- **A Identity resolution (§4.6.1, §0.4, §5.6):** canonical `patient_ref` = `patient:{id}` หรือ fallback `phone:{normalized_phone}`; ห้ามใช้ชื่อ; ยังไม่ link identity → notification เป็น pull/log เท่านั้น (กัน push ไม่มีผู้รับ)
- **D called-timeout (§4.9 `call_timeout_min` DEFAULT 5, §5.3, §5.4, Phase 2.5):** ปิด stale `called` คืน capacity (กัน deadlock); ทำใน sweeper + preflight ของ call_next
- **H async critical push (§5.6, §5.7, §10, Phase 4):** `queue_turn`/`queue_near` enqueue ผ่าน worker/RQ เท่านั้น (ไม่ sync ใน staff request); worker โหลด `MESSAGING_ENCRYPTION_KEYS`
- **G timezone (§0.4, §5.3):** session `DATE + TIME` materialize/compare ใน tenant tz (default `Asia/Bangkok`)
- **B estimator caveat (§5.5):** `count_ahead` ยังเป็น positional (queue_number) ไม่ priority-aware → under-estimate walk-in; แก้เป็น class-aware ภายหลัง (level 3) ผ่าน factory
- **C cold-start (§5.5):** `DEFAULT_SERVICE_MINUTES = 10.0` (implemented) + เสนอ config + min-sample threshold
- **E queue_number (§5.2, §10):** ตัด "sequence ต่อ (sp,date)" ออก เหลือ counter table (แนะนำ) หรือ advisory lock + `MAX()+1`
- **F §4.7 ↔ Phase 4.0 (§4.7):** §4.7 = target final schema; Phase 4.0 = idempotent upgrade migration สำหรับ table ที่สร้างก่อน 15 มิ.ย.
- **จุดเล็ก:** `_window_proximity` คืน 0 เมื่อไม่ใช่ appointment (implemented, §5.4); PWA VAPID คง per-tenant เพื่อ white-label (§6.5); re-queue หลัง skipped = Phase หลัง channel (§3.2); Telegram pool race ใส่ re-check ตอน `register_bot()` (§4.11)
- **ลำดับ implement ที่ล็อก:** patch แผน (นี้) → code `called-timeout` + `identity resolution contract` → แล้วค่อย Phase 4.0/4.13 notification wiring

---

*จบเอกสารแผน — เริ่มที่ Phase 0 และอ่านส่วนที่ 0 + 1 ก่อนเขียน code เสมอ*
