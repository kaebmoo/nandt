# Claude Code — Kickoff Prompt (28 มิ.ย. 2026)
# งาน: implement Backlog specs §15 — queue_near detector + reminder scheduler + RBAC enforcement
# คัดลอกทั้งบล็อกด้านล่างวางเป็น prompt แรกให้ Claude Code

---

คุณกำลังทำงานบน repo `nandt/hospital-booking` (NudDee SaaS). อ่าน
`docs/NudDee_Queue_and_Messaging_Implementation_Plan.md` **ส่วน §0 (CRITICAL RULES) + §1 ให้จบก่อนแตะ code เสมอ**
งานรอบนี้คือ implement **§15 Backlog specs** (queue_near detector / reminder scheduler / RBAC enforcement) ให้ครบ
โดยไม่ละเมิด §0 และไม่ re-litigate decisions ที่ล็อก (§2). อ่าน §15.1/§15.2/§15.3 เป็น spec หลักของแต่ละข้อ
และ §1.4 / §1.4.1 เพื่อรู้สถานะปัจจุบัน (Phase 0–5 + Patch 21 เสร็จ + merge+push origin/main แล้ว, migration ครบ 4 tenants)

**Out of scope:** AI/ML Roadmap (Track A/B/C/D), Platform Integration (Telemed handoff), UI React port, unskip — ทั้งหมด defer ไม่ต้องทำ.
ทุกอย่างที่แตะ LLM = defer.

## กฎเหล็กที่ห้ามพลาด (สรุปจาก §0/§10 — อ่านของจริงประกอบ)
- **Flask-first:** business logic อยู่ Python, render Jinja2 server-side; ห้ามผลัก logic ไป JS
- **FastAPI tenant pattern:** ถ้าแตะ FastAPI — `bind_tenant(db, schema)` + `SET search_path` ต้นฟังก์ชัน, commit ท้ายงาน, `Depends(get_db)`, resolve schema จาก `public.hospitals.schema_name` (ห้าม hardcode `tenant_{subdomain}`). รอบนี้ส่วนใหญ่เป็น Flask/Celery ไม่ใช่ FastAPI
- **queue_events append-only** ทุก state transition (ห้าม update/delete)
- **push critical (`queue_turn`/`queue_near`) enqueue ผ่าน worker/RQ เท่านั้น** ห้าม sync ใน staff request; worker โหลด `MESSAGING_ENCRYPTION_KEYS`
- **timezone:** เทียบเวลา materialize ใน `Asia/Bangkok` เสมอ (สำคัญมากกับ reminder window)
- **migration:** `SET search_path TO "<schema>";` ก่อน DDL; `ADD COLUMN IF NOT EXISTS` (idempotent); เพิ่ม column ใหม่ต้องใส่ทั้ง **model + canonical `add_queue_messaging_structures.py` (กัน drift test) + ALTER migration แยก** แล้วรัน default `tenant_humnoi` ก่อน, ตามด้วย `--all` เมื่อ verify
- **identity gate (§4.6.1/§5.6):** unlinked patient → pull/log เท่านั้น ห้าม push
- UI/ข้อความ = ไทย, identifier = อังกฤษ
- **pytest baseline ปัจจุบัน `165 passed` — ห้าม regress**; เพิ่ม test ทุกฟีเจอร์ใหม่ (real Postgres, ใช้ fixtures ใน `tests/conftest.py`: `db`/`make_session`/`service_point` ที่ bind_tenant แล้ว)
- debug codebase: `grep`/`search_files` หา pattern ชื่อฟังก์ชัน อย่าอ่านทั้งไฟล์
- งานนี้อยู่บน `main` ที่ push แล้ว → **แตก branch ใหม่ก่อนเริ่ม** (เช่น `feat/queue-backlog-specs`), commit ย่อยทีละข้อ, ไม่ push จนเจ้าของสั่ง

## ลำดับงาน (ทำตามลำดับ, commit ย่อยทีละข้อ, รัน pytest ทุกข้อ)

### 1. queue_near near-detector — §15.1
- migration: `ALTER TABLE queue_policy ADD COLUMN IF NOT EXISTS near_threshold INT DEFAULT 2;` (model + canonical DDL + ALTER แยก + idempotent); 0/NULL = ปิด
- หลัง `priority_service.call_next()` เรียกคนถัดไปสำเร็จ → สแกน `status='checked_in'` ของ sp เดียวกัน, position = `queue_service.count_ahead(...)`; `0 < position <= near_threshold` และยังไม่เคยส่ง → `enqueue_queue_near` (มีอยู่แล้ว) ผ่าน RQ
- กันส่งซ้ำพึ่ง dedupe เดิมของ `notify()` (advisory lock + notification_log); identity gate เหมือน queue_turn
- ticket url สร้างตอน enqueue ใน `queue_routes.call_next` (เหมือน queue_turn)
- **Acceptance:** entry ที่เพิ่งเข้าเขต ≤ threshold ได้ `queue_near` ครั้งเดียว (ไม่ซ้ำข้ามรอบ); unlinked → log ไม่ push; near_threshold=0 → ไม่ยิง; tests ครอบ เข้าเขต/ไม่เข้า/ไม่ซ้ำ/gate

### 2. Reminder scheduler — §15.2
- ใช้ `appointments.reminder_sent`/`reminder_sent_at` ที่ **มีอยู่แล้ว** เป็น dedupe (ไม่ต้องสร้างใหม่)
- (optional) migration `messaging_config.reminder_lead_hours INT DEFAULT 24` (ไม่ทำก็ hardcode 24)
- Celery `@shared_task(name="tasks.send_all_tenant_reminders")` ใน `flask_app/app/tasks.py` ตามแพตเทิร์น `sync_all_tenant_*` (loop `HospitalStatus.ACTIVE`, bind tenant, reset search_path ก่อน close) + beat entry ใน `flask_app/app/__init__.py` `beat_schedule` (เช่นรายชั่วโมง)
- ต่อ tenant: ถ้า `reminder_enabled`=false ข้าม; query appointments `start_time` ในกรอบ `[now+lead, now+lead+window]` (Asia/Bangkok) ที่ `reminder_sent=false` → resolve patient_ref → enqueue `notify(urgency='low', event_type='reminder')` ผ่าน RQ → set `reminder_sent=true, reminder_sent_at=now`
- low urgency เลือกช่องฟรีก่อน, unlinked → ส่งไม่ได้
- **Acceptance:** นัดในกรอบ + linked + reminder_enabled → reminder 1 ครั้ง + `reminder_sent=true`; reminder_enabled=false → ไม่ส่ง; รัน job ซ้ำ → ไม่ส่งซ้ำ; tests ครอบ window/dedupe/gate

### 3. RBAC enforcement — §15.3 (cross-cutting, branch/patch แยกก็ได้)
- `UserRole` ตอนนี้มีแค่ `SUPER_ADMIN`, `HOSPITAL_ADMIN` — **ถ้าจะเพิ่ม role ละเอียด (staff/front-desk) ต้องถามเจ้าของก่อน** (เป็น decision + migration) อย่าเพิ่มเอง
- decorator `@require_role(*roles)` ใน `flask_app/app/auth.py` — อ่าน `get_current_user().role`, ไม่พอ → flash + redirect/403; ใช้ต่อจาก `@login_required` + tenant check เดิม; **ห้าม `db.close()` ใน decorator** (search_path)
- ทาบ route sensitive ก่อน: `settings/*` (availability, messaging), ลบ/แก้ template, analytics = `HOSPITAL_ADMIN`; staff console/check-in คงเดิม
- **Acceptance:** role ไม่พอเข้า admin-only route → ถูกปฏิเสธ (ไม่ 500, ไม่หลุด search_path); role พอ → เข้าได้; tests ครอบ allow/deny ต่อ role

## Definition of Done
- ทุก Acceptance ข้างบนผ่าน; `pytest` เขียว (≥165 + tests ใหม่)
- migration ใหม่รันบน `tenant_humnoi` ได้ (idempotent) + ตรวจ column; พร้อม note ว่าต้อง `--all` ตอน deploy
- ไม่มี business logic หลุดไป JS; push critical ผ่าน RQ; identity gate ครบ
- อัปเดต §1.4 / §1.4.1 ใน plan ว่าทำอะไรเสร็จ + commit hash (ย้าย ⚠️/future → ✅ done)

## วิธีทำงานกับ plan/ไฟล์
- แก้ plan: อ่านก่อนเขียน (anchor บรรทัดเดียว distinctive; dryRun ก่อน commit)
- เพิ่ม column ใหม่: model + canonical DDL + ALTER migration + drift test ต้องผ่าน (`tests/test_migration_drift.py`)
