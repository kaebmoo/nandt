# Prompt สำหรับส่งงานให้ Claude Code / Cowork — NudDee Queue & Messaging

## วิธีใช้ (ส่วนนี้ไม่ต้อง copy)
1. วางไฟล์ `NudDee_Queue_and_Messaging_Implementation_Plan.md` ไว้ใน repo (เช่น root หรือ `/docs`) เพื่อให้ Claude Code อ่านได้ — ถ้าวางที่อื่น แก้ path ในประโยคแรกของ prompt ให้ตรง
2. เปิด Claude Code/Cowork ในโฟลเดอร์ `/Users/seal/Documents/GitHub/nandt/hospital-booking/`
3. Copy **Kickoff prompt** ด้านล่างไปวาง (ใช้ครั้งเดียวตอนเริ่ม)
4. จบแต่ละ Phase agent จะหยุดรายงาน — ใช้ **Continuation prompt** เพื่อสั่งทำ phase ถัดไป

---

## ▼▼▼ KICKOFF PROMPT (copy ทั้งบล็อกนี้) ▼▼▼

คุณคือ senior engineer ที่จะ implement ฟีเจอร์ระบบคิว + check-in + การเชื่อมต่อ LINE/Telegram/PWA ของโปรเจกต์ NudDee SaaS (Flask port 5001 + FastAPI + PostgreSQL multi-tenant per-schema) ตามแผนที่เขียนไว้แล้ว ห้ามเริ่มเขียน code จนกว่าจะทำ 3 ข้อแรกเสร็จ

**ก่อนเริ่ม (ทำตามลำดับ):**
1. อ่านไฟล์แผน `NudDee_Queue_and_Messaging_Implementation_Plan.md` (อยู่ที่ root ของ repo หรือ /docs) ให้จบ โดยเฉพาะ ส่วนที่ 0 (CRITICAL RULES), ส่วนที่ 1 (Context), ส่วนที่ 2 (Decisions ที่ล็อก), ส่วนที่ 5 (Component contracts), ส่วนที่ 10 (สิ่งที่ห้ามทำ)
2. สำรวจ codebase จริง — ใช้ `search_files` กับ pattern ชื่อฟังก์ชัน (เช่น `def edit_template`) แทนการอ่านทั้งไฟล์ ดู key files ในส่วนที่ 1.3 ของแผน และ inspect schema จริงด้วย `\d <table>` อย่าเดาโครงสร้างเดิม
3. ยืนยันความเข้าใจกับฉันสั้น ๆ ว่าจะเริ่มที่ Phase 0 และเข้าใจกฎเหล็กครบ ก่อนลงมือ

**กฎเหล็กที่ห้ามฝ่าฝืน (สรุป — รายละเอียดในแผน ส่วน 0 + 10):**
- Flask-first: business logic อยู่ Python + Jinja2 server-side เท่านั้น ห้ามผลัก logic ไป JavaScript/AJAX (ยกเว้น SDK glue ที่ platform บังคับ + display ล้วน เช่น auto-refresh จอคิว, กราฟ)
- ทุก FastAPI endpoint ต้อง SET search_path ที่ต้นฟังก์ชัน (`db.execute(text(f'SET search_path TO "{schema_name}", public'))`) **โดยห้าม `db.commit()` ทันทีหลัง SET** (commit ที่ท้ายงานเท่านั้นถ้าเป็น write — ดูเหตุผลในแผนส่วน 0.2); ใช้ `Depends(get_db)` ห้ามใช้ `Depends(get_tenant_db)`
- `*.localhost` เป็น subdomain ที่ถูกต้อง, สร้าง URL ผ่าน `url_helper.py`, ห้าม hardcode `?subdomain=`
- token/secret ต้อง encrypt ด้วย Fernet ตาม spec 5.7 — ห้าม plaintext ใน DB/log, ห้าม hardcode key, key มาจาก env `MESSAGING_ENCRYPTION_KEYS`
- wait time คำนวณผ่าน `get_estimator(...).estimate(...)` เท่านั้น ห้าม inline ที่อื่น
- `queue_number` assign แบบ atomic (DB sequence ต่อ service_point+date หรือ lock) ห้าม `MAX()+1`
- `queue_events` เป็น append-only — ห้าม update/delete, ทุก status transition ต้อง insert event 1 แถว
- async LINE notification มีทางเดียวคือ push (เสียเงิน) — ห้ามพยายามเรียก free reply / liff.sendMessages จาก cron/background job
- date format `dd/mm/yyyy` (ใช้ Jinja2 filter `thai_date`)
- UI/ข้อความถึงผู้ใช้เป็นภาษาไทย, code/identifier เป็นอังกฤษ

**Workflow:**
- ทำทีละ Phase ตามลำดับ: 0 → 1 → 1B → 2 → 3 → 4 → 5
- แต่ละ task ต้องผ่าน acceptance criteria ที่ระบุในแผนก่อนถือว่าเสร็จ
- เขียน unit test ตามส่วนที่ 9.2 ของแผน สำหรับ logic หลัก (grace classify, priority/ratio + starvation, estimator, dispatcher channel+cost, transition+event, check-in concurrency)
- migration รันบน schema `tenant_humnoi` ก่อน ทดสอบด้วย `psql -d nuddee` → `SET search_path TO tenant_humnoi;`
- **จบแต่ละ Phase ให้หยุดแล้วรายงาน:** สรุปสิ่งที่ทำ, ผล acceptance criteria รายตัว, ไฟล์ที่แก้/สร้าง, และอะไรที่ค้างหรือต้องตัดสินใจ แล้วรอฉันยืนยันก่อนไป Phase ถัดไป

**เมื่อไม่แน่ใจ / ต้องตัดสินใจ — ถามก่อน อย่าเดา:**
- ห้าม re-litigate decisions ในส่วนที่ 2 ของแผน ถ้าจะเบี่ยงต้องถามฉันพร้อมเหตุผล
- จุดที่ต้องหยุดถามฉันก่อนทำแน่ ๆ:
  - (ก) mapping service_point ↔ availability template เฉพาะกรณี repo/DB ที่กำลังทำงานยังไม่มี `service_points.availability_template_id` เท่านั้น; ในสถานะล่าสุดของ repo นี้ Phase 1B.0 ตัดสินและ implement แล้ว
  - (ข) การ ALTER ตารางเดิม (`appointments`, `availabilities`) — ยืนยันกับฉันทุกครั้งก่อนรัน
  - (ค) ถ้างานต้องพึ่งหน้า template edit ที่ปุ่ม save ยังพังอยู่ (แผนส่วน 1.5) ให้แจ้งก่อน

เริ่มเลย: อ่านแผน + สำรวจ codebase + inspect schema จริง แล้วยืนยันความเข้าใจกับฉัน จากนั้นเริ่ม Phase 0

## ▲▲▲ จบ KICKOFF PROMPT ▲▲▲

---

## ▼ CONTINUATION PROMPT (ใช้ซ้ำทุกครั้งที่ขึ้น Phase ใหม่ — แก้เลข Phase) ▼

ทำ Phase __ ต่อตามแผน `NudDee_Queue_and_Messaging_Implementation_Plan.md` โดยรักษากฎเหล็กเดิมทุกข้อ (Flask-first, FastAPI SET search_path, encrypt token, get_estimator, atomic queue_number, append-only queue_events, async LINE = push เท่านั้น)

- ทำทุก task ใน Phase นี้ให้ผ่าน acceptance criteria ที่ระบุ
- เขียน unit test ตามส่วนที่ 9.2 สำหรับ logic ที่เพิ่ม
- ถ้าเจอจุดต้องตัดสินใจ (mapping / ALTER ตารางเดิม / schema เดิมไม่ตรงแผน) ให้หยุดถามฉันก่อน
- จบ Phase แล้วรายงาน: สิ่งที่ทำ + ผล acceptance รายตัว + ไฟล์ที่แก้ + อะไรที่ค้าง แล้วรอฉันยืนยันก่อนไปต่อ

## ▲ จบ CONTINUATION PROMPT ▲

---

## เคล็ดลับ (ไม่ต้อง copy)
- ถ้า agent เริ่มเขียน JS logic, ลืม SET search_path, หรือคำนวณ wait แบบ inline — เตือนกลับด้วยกฎข้อนั้นในแผน ส่วน 0/10
- อยากให้ทำหลาย phase รวดเดียวโดยไม่หยุดรายงาน: บอกเพิ่มว่า "ทำ Phase 0 ถึง 1B รวดเดียว รายงานครั้งเดียวตอนจบ 1B" — แต่แนะนำหยุดรายงานทุก phase ช่วงแรกเพื่อจับ regression เร็ว
- Phase 4 (channels) เริ่มขนานหลัง Phase 0 ได้ ถ้าอยากเร่ง LINE gateway ก่อน — แต่ event แจ้งเตือนคิว (4.7) ต้องรอ Phase 1-3 พร้อม
