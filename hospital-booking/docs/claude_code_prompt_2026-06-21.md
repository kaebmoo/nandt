# Claude Code — Kickoff Prompt (21 มิ.ย. 2026)
# งาน: implement Patch 21 มิ.ย. 2026 (console HTMX + เสียง WAV + anon identity + arrived_ack)
# คัดลอกทั้งไฟล์นี้วางเป็น prompt แรกให้ Claude Code

คุณกำลังทำงานบน repo `nandt/hospital-booking` (NudDee SaaS). อ่าน
`docs/NudDee_Queue_and_Messaging_Implementation_Plan.md` **ส่วนที่ 0 + 1 ให้จบก่อนแตะ code เสมอ**
งานรอบนี้คือ implement decision ใน **"Patch 21 มิ.ย. 2026"** (อยู่ก่อน §13/§14 ท้ายเอกสาร) ให้ครบ
โดยไม่ละเมิด CRITICAL RULES (§0) และไม่ re-litigate decisions ที่ล็อก (§2)

**Out of scope รอบนี้:** Track C/D (feedback insight, assistant) และทุกอย่างที่แตะ LLM = defer ไม่ต้องทำ. เอกสารสามไฟล์ (Queue plan, `NudDee_AI_ML_Roadmap.md`, `NudDee_Platform_Integration_Plan.md`) sync ตรงกันแล้ว ณ 21 มิ.ย. 2026 — ถ้าแก้ contract ใด ๆ (เช่น patient_ref, state machine) ให้ update cross-reference ทั้งสามไฟล์

## กฎเหล็กที่ห้ามพลาด (สรุปจาก §0/§10 — อ่านของจริงประกอบ)
- Flask-first: business logic อยู่ Python (Flask+FastAPI), render Jinja2 server-side. ห้ามผลัก logic ไป JS
  - **ข้อยกเว้นเดียวรอบนี้:** HTMX บน **staff console** เท่านั้น (AJAX-swap-fragment, server render HTML, logic ยังอยู่ Python) — ดู §13
- FastAPI ทุก endpoint: `bind_tenant(db, schema)` + `SET search_path` ที่ต้นฟังก์ชัน, commit ท้ายงาน, ใช้ `Depends(get_db)` (ห้าม `get_tenant_db` factory), resolve schema จาก `public.hospitals.schema_name` (ห้าม hardcode `tenant_{subdomain}`)
- ทุก state transition ต้อง insert `queue_events` (append-only, ห้าม update/delete)
- push critical (`queue_turn`/`queue_near`) enqueue ผ่าน worker/RQ เท่านั้น (ห้าม sync ใน staff request); worker โหลด `MESSAGING_ENCRYPTION_KEYS`
- timezone: session `DATE+TIME` materialize/compare ใน `Asia/Bangkok`
- migration: `SET search_path TO tenant_humnoi;` ก่อนรัน DDL; ใช้ `ADD COLUMN IF NOT EXISTS` (idempotent); ตรวจ existing ก่อน ALTER
- UI/ข้อความ = ไทย, identifier = อังกฤษ
- pytest baseline ปัจจุบัน `144 passed` — **ห้าม regress**; เพิ่ม test ทุกฟีเจอร์ใหม่
- debug codebase: `search_files` หา pattern ชื่อฟังก์ชัน อย่าอ่านทั้งไฟล์
- LLM provider boundary (AI/ML §0.9): งานรอบนี้ไม่แตะ LLM; แต่ถ้าเจอ code path ที่จะส่ง patient free-text ไป LLM ห้ามต่อ external — `llm_provider` default `none`, เปิดแล้วแนะนำ `self_hosted`, `external` opt-in เฉพาะ tenant ที่มี consent+DPA

## ลำดับงาน (ทำตามลำดับ, commit ย่อยทีละข้อ, รัน pytest ทุกข้อ)

### 1. anon identity (`anon:{token}`) — §4.6.1
- เพิ่ม resolver กลาง (เช่น `services/identity.py`): order `patient:{id}` → `phone:{normalized_phone}` → `anon:{token}`
  - `token` = `secrets.token_urlsafe(16)` (≥22 chars), unique ต่อ visit, **ห้าม derive จาก PII**
- walk-in / QR scan ที่ไม่มี `patients.id` และไม่ให้เบอร์ → ออก `anon:{token}` เป็น `patient_ref` (แก้ NOT NULL gap)
- `channel_links` ผูก `anon:{token}` ↔ Telegram chat_id / PWA subscription ได้ (PII-free)
- **notify() identity gate:** `anon:{token}` ที่มี `channel_links` active = addressable → push ได้; ถ้าไม่มี channel → pull/log
- **ห้าม** เพิ่ม `identity_mode` field (force zero-PII = defer per decision)
- Acceptance: walk-in ไม่มีเบอร์ check-in สำเร็จ (มี patient_ref ถูกต้อง); anon+linked → push ได้; anon ไม่ linked → log `pull`/`skipped` ไม่ push. tests ครอบ resolver order + gate กับ anon

### 2. arrived_ack — §3.2 + §4.4
- migration: `ALTER TABLE queue_entries ADD COLUMN IF NOT EXISTS arrived_ack_at TIMESTAMPTZ;` (ทุก tenant schema)
- `queue_events.event_type` รับค่า `arrived_ack` (actor `patient`|`staff`)
- action ที่ status page (magic-link, patient เขียนกลับได้) + ปุ่ม staff กดแทน → set `arrived_ack_at` + insert event; **ไม่ใช่ status ใหม่, ไม่ใช่ gate**
- **แก้ `queue_service.close_stale_called()` + call_next preflight:** ยกเว้น entry ที่ `arrived_ack_at IS NOT NULL` (ห้ามปิดเป็น stale/no_show)
- Acceptance: กด ack แล้ว sweeper ไม่ปิด entry นั้น; event ถูก log; tests ครอบ ack(patient/staff) + sweeper exclusion

### 3. Staff Console (HTMX) — §13
- route ใหม่ `flask_app/app/queue_routes.py`: หน้า console ต่อ `service_point` (+ overview optional), Jinja2
- ทุก action → `services/queue_service.py` (logic Python) → `queue_entries` + `queue_events(actor='staff')`
- HTMX: ปุ่ม `hx-post` → route → `queue_service.transition()` → return **fragment ที่ server render** (การ์ดห้อง/แถว) → swap เฉพาะส่วน
  - แยก template fragment ให้ route ตอบกลับได้ (เช่น `templates/queue/_room_card.html`)
  - refresh: `hx-trigger="every Ns"` (วาง seam ไป SSE ภายหลัง)
- ปุ่มหลัก "เรียกคิวถัดไป" ระดับห้อง; รายคิว: start/done/no_show/skip/reclass/move(service_point_id)/reset-to-waiting(called→checked_in)/show QR/log/remove
- **`call_next` ต้อง atomic** (advisory lock หรือ `SELECT ... FOR UPDATE`) กัน 2 สเตชันคว้าคนซ้ำ
- destructive (remove/no_show) ต้อง confirm; badge "ถึงแล้ว" เมื่อมี `arrived_ack_at`; Bootstrap 5 responsive
- Acceptance: action update การ์ดโดยไม่ reload ทั้งหน้า; route ไม่มี decision ใน JS; concurrent call_next ไม่ได้คนซ้ำ; pytest ครอบ transition + atomic

### 4. เสียงเรียกคิว (WAV concatenation) — §14
- config ต่อ tenant **แค่ 2 อย่าง**: (ก) clip library (โฟลเดอร์ WAV ต่อ schema, อัปโหลดผ่าน settings) (ข) template (ลำดับ token เช่น `["call_prefix","{queue}","room_prefix","{room}"]`)
- playlist builder (Python): literal → `{name}.wav`; placeholder `{queue}`/`{room}` → หา `{ค่าเต็ม}.wav` ก่อน, **ไม่เจอ fallback อ่านทีละหลัก** (`3.wav 5.wav ...`)
- หน้า display (Jinja2 บน TV) เล่น playlist (display-only): autoplay-unlock (ปุ่ม "เริ่มระบบเสียง" 1 ครั้ง), audio queue เล่นทีละประกาศไม่ทับ, preload clips
- default ชุดไทยมาให้: `0-9.wav` + `call_prefix.wav`("เชิญหมายเลข") + `room_prefix.wav`("ที่ห้อง")
- **ไม่อ่านตัวอักษร series (L)** ใน default; per-tenant toggle เปิด/ปิดต่อห้อง + ความดัง + จำนวนครั้งซ้ำ
- Acceptance: เรียกคิว → เล่นถูก; ไม่มีไฟล์เต็ม → fallback ทีละหลัก; unlock ทำงาน; ถี่ไม่ทับ; เปลี่ยน template/clip ไม่ต้องแตะ code; tests ครอบ playlist builder (เต็ม/fallback)

### 5. ตามคนไข้ (pull/push wiring) — §5.6 ภาคผนวก
- ยืนยัน status page (pull) แสดง เลขคิว/สถานะ/คนข้างหน้า/เวลารอ; push near/turn เดินตาม `channel_priority`
- ไม่ต้องสร้างใหม่ถ้ามีแล้ว — เช็คว่า 5 ทาง (pull/push/จอ+เสียง/arrived_ack/manual) เชื่อมครบ

## Definition of Done
- ทุก Acceptance ข้างบนผ่าน; `pytest` เขียว (≥144 + tests ใหม่)
- migration รันบน `tenant_humnoi` ได้ (idempotent), ตรวจ `\d queue_entries` มี `arrived_ack_at`
- ไม่มี business logic หลุดไป JS (ยกเว้น HTMX-swap ของ console ตามที่ระบุ)
- อัปเดต §1.4 (Current State) ใน plan ว่าทำอะไรเสร็จ + commit hash

## วิธีทำงานกับ plan/ไฟล์
- แก้ plan: อ่านก่อนเขียน (anchor บรรทัดเดียว distinctive; DDL anchor บน comment ก่อนจุดแทรก; dryRun ก่อน commit)
- ถ้าติดปุ่ม save หน้า template edit (§1.5 known issue) และงานไม่พึ่ง → ข้ามได้
