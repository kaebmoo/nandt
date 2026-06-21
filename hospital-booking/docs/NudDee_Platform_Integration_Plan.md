# NudDee SaaS — แผน Platform Integration: Handoff Contract กับระบบหลังบ้านเฉพาะทาง

> **เอกสารนี้คืออะไร:** contract ที่ระบบเฉพาะทาง (เช่น telemed, ระบบทันตกรรม, แล็บ) เสียบเข้า NudDee ในฐานะ "หลังบ้าน" (handler) — โดย NudDee ทำหน้าที่ "ประตูหน้าบ้าน"
> **ขอบเขต:** นิยาม journey, สามชนิดข้อความของ contract (handoff / lifecycle event / patient_payload), ซองที่ล็อก, และเส้นแบ่งความเป็นเจ้าของข้อมูล
> **สถานะ:** **design ล็อกแล้ว — build deferred** จนกว่าจะมี demand จริง (รูปแบบเดียวกับ [`docs/NudDee_AI_ML_Roadmap.md`](./NudDee_AI_ML_Roadmap.md) ที่เป็น Phase 5+) เราล็อก "ซอง" ตอนนี้เพื่อไม่ปิดประตูอนาคต ส่วน "ไส้ใน" ปล่อยเปิดไว้
> **อ่านก่อน:** §0 (Flask-first + tenant schema), §4.6.1 (identity), §0.5 (ต้นทุน LINE) ของ [`NudDee_Queue_and_Messaging_Implementation_Plan.md`](./NudDee_Queue_and_Messaging_Implementation_Plan.md) — เอกสารนี้ต่อยอดจากของพวกนั้น ไม่ทับ

---

## 0. ตำแหน่งของ NudDee (เหตุผลที่ contract หน้าตาแบบนี้)

NudDee = **engagement / edge layer (ประตูหน้าบ้าน)** ไม่ใช่ระบบกลางที่ทุกอย่างต้องวิ่งผ่าน และไม่ใช่ HIS

- **NudDee เป็นเจ้าของ patient-facing layer:** LINE OA (operate ให้ ร.พ.), identity graph ของคนไข้, คิวที่คนไข้เห็น (เลขคิว/ETA), check-in, การแจ้งเตือน
- **handler (หลังบ้าน) เป็นเจ้าของงานเฉพาะทาง:** เช่น Telemed = video consult (Google Meet), พยาบาลซักประวัติ/สัญญาณชีพ, แพทย์วินิจฉัย — NudDee ไม่แตะ ไม่เก็บ
- **Triage board ภายในของ handler ≠ คิวคนไข้ของ NudDee** — อันหนึ่ง staff/clinical ดู อันหนึ่งคนไข้ดู อยู่ร่วมกันได้เพราะคนละผู้ชม
- สอดคล้องกับ **decision #2** ของ main plan: LINE/Telegram = ทางผ่านเข้าแอป ไม่ใช่ท่อ push — และขยายเป็น "NudDee = ทางผ่านเข้าทุกบริการของ ร.พ."

**นัยเชิงกลยุทธ์ (ดู §9):** ขายความเป็น front door ผ่านบริการที่เชื่อมง่ายก่อน (OPD/ทันตกรรม) เพื่อสะสมมวลคนไข้บน LINE OA ของ ร.พ. แล้วระบบเฉพาะทางอย่าง Telemed ค่อยถูกดูดเข้ามาเป็น integration ทีหลัง — ไม่ใช่ไปง้อตั้งแต่ยังไม่มีอะไรในมือ

---

## 1. หลักการออกแบบ — ทำไม contract ที่ "บาง" คือ contract ที่ "ครอบคลุมที่สุด"

หลักที่ฟังดูย้อนแย้งแต่จริง: **วิธีทำให้ contract รองรับทุกกรณี ไม่ใช่การไล่รองรับทุกกรณี แต่คือการทำให้มันบางจนไม่มี domain ของกรณีไหนอยู่ในนั้นเลย** ยิ่งยัดให้ contract รู้จัก telemed/OPD/แล็บ มากเท่าไหร่ มันยิ่งผูกกับกรณีพวกนั้นและยิ่งเปราะ

**field มีสองตระกูล:**
- **ซอง (envelope)** — โครงสร้างที่กลไก async/retry **บังคับ**ให้มี (ไม่ใช่รสนิยม) → **ล็อกตอนนี้** (§4) เพราะแก้ทีหลังแพง
- **ไส้ใน (interior)** — ของ domain (อาการ, Meet link, สัญญาณชีพ) → **เป็น blob ทึบที่ NudDee ไม่ parse** (§5) ไม่ต้อง spec; ของเฉพาะทางห้ามโผล่ใน contract

**YAGNI:** handoff เป็น optional ต่อ service (§6 เคส 3); ของในรายการ §7 ห้ามสร้างจนกว่า demand จริงจะดึงออกมา

---

## 2. แนวคิดแกน: `journey`

NudDee เป็นเจ้าของ `journey` = การเดินทางของคนไข้ผ่าน **หนึ่งบริการ หนึ่งครั้ง**

| field | ความหมาย |
|---|---|
| `journey_id` | correlation id ของ NudDee เอง, **opaque**, วิ่งครบ end-to-end (ดูเหตุผล §4) |
| `service_type` | tag ของบริการ เช่น `telemed` / `opd` / `dental` (แค่ป้าย ไม่ใช่ logic) |
| `external_ref` | **opaque token** ที่ยื่นให้ handler ใช้อ้างกลับ — **ไม่ใช่** `patient_ref`/เบอร์โทรดิบ; map ภายในกับ `patient_ref` (§4.6.1 main plan) |
| `state` | สถานะ journey — **ต่อยอด** queue lifecycle (§5 main plan) ไม่ redefine |

**ความสัมพันธ์:** `1 patient_ref → many journeys` (ต่อบริการ/ต่อครั้ง); `1 journey → ≤ 1 active handler`

**state ของ journey** ไม่เขียน state machine ใหม่ชนกับคิว — queue states (`checked_in`/`called`/`in_service`/`no_show`/`skipped`/`done` ตาม §3.2 main plan) ยังเป็นของ queue engine; journey แค่เพิ่มชั้นบน: `handed_off` (ส่งให้ handler แล้ว) และ `returned`/`completed` (handler รายงานจบ) สำหรับบริการที่มี handler

---

## 3. Contract: สามชนิดข้อความ (= ทั้งหมดของ surface)

ลูกศรสามเส้นนี้คือ contract ทั้งหมด ทุกอย่างนอกนั้นเป็นเรื่องภายในของแต่ละระบบ

### 3.1 `handoff` (NudDee → handler, outbound)

NudDee POST ไปยัง endpoint ที่ handler ลงทะเบียนไว้ (§3.4) เมื่อถึง handoff trigger

```json
POST {handler.endpoint_url}
Authorization: <credential ของ handler ที่เก็บใน registration row>
{
  "contract_version": "1.0",
  "journey_id": "jr_8f3a2c...",          // opaque, NudDee-owned
  "external_ref": "ext_q9z1k...",        // opaque handle (ไม่ใช่ patient_ref/เบอร์)
  "service_type": "telemed",
  "context": {                           // blob เปิด — patient-entered, NudDee ไม่ตีความ
    "symptoms": "ปวดจุกแน่นท้อง มารักษากลางคืน",
    "appointment_time": "2026-06-20T15:00:00+07:00"
  },
  "callback_url": "https://<tenant>.nuddee.app/v1/journeys/jr_8f3a2c.../events",
  "idempotency_key": "ho_3c7e9a..."
}
```

- handler ตอบ **2xx = รับเคสแล้ว**
- ส่งผ่าน **RQ worker + retry + dead-letter** (ใช้ worker ของ Phase 4, §0.5/§10 main plan) — ห้ามยิง sync ในrequest ของ staff
- **handoff trigger** = property ของ registration; **default = check-in** (ยืนยันการมาถึง) สำหรับบริการแบบเข้าคิว — เปลี่ยน trigger ภายหลัง (เช่นแล็บ handoff ตอน `called`) = แก้ registration field ไม่กระทบรูปซอง

### 3.2 `lifecycle event` (handler → NudDee, callback/inbound)

handler POST กลับมาที่ `callback_url` (ผูก `journey_id` อยู่แล้ว)

```json
POST /v1/journeys/{journey_id}/events
Authorization: <API key ของ tenant — resolve schema จาก key เท่านั้น, §4>
{
  "contract_version": "1.0",
  "event_type": "ready",
  "idempotency_key": "ev_5a2d1f...",
  "patient_payload": { ... }             // เฉพาะ event_type=ready (ดู §3.3)
}
```

`event_type` เป็น **เซ็ตปิดเล็ก ๆ** (ไม่เพิ่มตามบริการ):

| event_type | ความหมาย / ผลที่ NudDee ทำ |
|---|---|
| `accepted` | handler รับเคสแล้ว (ack handoff แบบ async) → journey = `handed_off` |
| `status` | อัปเดตสถานะหยาบ ๆ (optional) — สะท้อนให้ staff/คนไข้ดูเฉย ๆ |
| `ready` | ถึงจังหวะคนไข้ต้องทำอะไร → พก `patient_payload` (เช่น Meet link) → NudDee ส่งให้คนไข้ |
| `completed` | จบ encounter → journey = `completed` → ส่ง post-visit notify (นัดติดตาม/แจ้งผล) |
| `failed` | handler ทำไม่ได้ → NudDee fallback / แจ้ง staff |

- **idempotency_key** กัน callback ซ้ำ; **reject event ที่ `journey_id` ไม่ match** (กัน cross-journey)

### 3.3 `patient_payload` (พกบน `ready` — หัวใจของความเป็น platform)

นี่คือ primitive เดียวที่ทำให้ NudDee "ส่งอะไรก็ได้ให้คนไข้ โดยไม่ต้องรู้ว่ามันคืออะไร"

```json
"patient_payload": {
  "type": "link",                        // NudDee route เข้า renderer ตาม type นี้
  "delivery_hint": "urgent",             // คำใบ้ช่อง/ความเร่งด่วน (optional)
  "content": {                           // NudDee ไม่เข้าใจเนื้อใน
    "url": "https://meet.google.com/xxx-yyyy-zzz",
    "label": "เข้าห้องตรวจ Telemedicine"
  }
}
```

- NudDee **ไม่ parse `content`** → route เข้า **channel renderer ตาม `type`** → ส่งผ่าน **notify path เดิม** (`channel_links` + `notify_service`, Phase 4) ไม่สร้างระบบส่งใหม่
- **`type` → renderer (1:1, เพิ่มเมื่อมีของจริง):** Telemed = `link`; อนาคต = `queue_number` (OPD), `room` (ทันตกรรม), `document` (แล็บ) — ช่องเดียวกันหมด เป็น strategy seam แบบเดียวกับ `get_estimator()`
- **ต้นทุน (§0.5 main plan):** ส่ง payload ผ่าน LINE แบบ async = **paid push**; Telegram/PWA ฟรี — inherit cost model เดิม ไม่มีข้อยกเว้น
- **`delivery_hint` เป็นแค่คำใบ้** — NudDee ตัดสินช่องจริงเองตาม `channel_links` + policy ของ tenant; **handler สั่งช่องไม่ได้**

### 3.4 handler registration

config row ต่อ (tenant, service_type):

```
(tenant, service_type) → { endpoint_url, auth_credential, contract_version, handoff_trigger }
```

เพิ่ม handler/บริการใหม่ = **+1 row + หลังบ้านทำสามข้อความข้างบน** — **ไม่มี developer portal** (ดู §7)

---

## 4. ซองที่ล็อก — แต่ละ field ผูกกับความพังที่มันกัน (mechanics บังคับ ไม่ใช่รสนิยม)

| field / กฎ | กันความพังอะไร |
|---|---|
| `journey_id` วิ่งครบ end-to-end | ถ้าไม่มี → match callback กลับ journey ไม่ได้ (ตระกูลเดียวกับบั๊ก `patient_ref` ที่ silent push fail, §4.6.1) |
| `idempotency_key` **ทั้งสองทิศ** | network retry สร้างเคสซ้ำ / ยิง LINE ซ้ำ (ซ้ำ = เสียเงิน §0.5) |
| `contract_version` ทุกข้อความ | retrofit versioning ทีหลังแพงมาก; ใส่ตั้งแต่แรกแทบฟรี |
| `external_ref` เป็น opaque (ไม่ใช่ `patient_ref`/เบอร์) | กัน PII รั่วออกหลังบ้าน + decouple handler จากโครงสร้างภายในของเรา |
| **API key ผูก tenant, resolve schema จาก key เท่านั้น — ห้ามรับ tenant id จาก body** | **cross-tenant data breach** — ยกบทเรียน `search_path`/`bind_tenant` (§0.2) จาก "regression" ขึ้นเป็น "security boundary" บน public surface |
| handoff outbound มี **retry + dead-letter** (RQ) | handler ล่ม → คนไข้ค้างกลาง journey |
| **audit log** ทุกการเคลื่อนข้อมูลข้ามขอบ | PDPA — ต้องตรวจย้อนได้ว่าใครส่งอะไรให้ใครเมื่อไหร่ |
| `context` พกแค่ **patient-entered start data**; **ผลคลินิกไม่ไหลกลับมาเก็บ** | PDPA data minimization + ไม่ใช่งานของ NudDee (เก็บมาเปล่า ๆ มีแต่ภาระ compliance) |

---

## 5. ไส้ในแบบทึบ (opaque interior)

- `context` (ขาออก) และ `patient_payload.content` (ขาเข้า) = **blob ที่ NudDee ไม่ parse**
- **ทำไม:** (ก) ทำให้ contract generic จริง — ของเฉพาะทางไม่รั่วเข้า core; (ข) **ไม่ปิดประตู HL7 FHIR ในอนาคต** — วันหน้า map `context`/`payload` ไป FHIR resource ได้โดย**ไม่ต้อง commit FHIR ตอนนี้** (ซึ่งจะ over-engineer หนักสำหรับสเกลปัจจุบัน)
- **เส้นข้อมูลที่ห้ามข้าม:** NudDee **ไม่เก็บ clinical result** (สัญญาณชีพ / คำวินิจฉัย / ฟิล์ม / ยา) — อยู่ในหลังบ้านเท่านั้น; ขาเข้ารับแค่ "เสร็จแล้ว" + next-step

---

## 6. Stress test — พิสูจน์ว่าซองแบกเคสที่ไม่ได้วางแผน โดยไม่แก้ schema

| # | scenario | ซองมีรูไหม | ซองปิดประตูไหม | verdict |
|---|---|---|---|---|
| 1 | หลังบ้านต้อง **ขอข้อมูลจากคนไข้ก่อนเริ่ม** (เช่น Telemed ขอรูปบัตรก่อนวิดีโอคอล) | **มีรู** — event เป็น push ทางเดียว ขอ input แล้วส่งคำตอบกลับไม่ได้ | **ไม่ปิดประตู** — `journey_id` + registration มีแล้ว → อนาคต = +1 event type + 1 endpoint รับคำตอบ | **ไม่ build ตอนนี้** (เปลี่ยน NudDee เป็น broker สองทาง = ของใหญ่) |
| 2 | คนไข้ **ยกเลิกหลัง handoff ไปแล้ว** — handler ถือเคสของคนที่เดินออกไป | **เผย asymmetry** — ขาเข้ามี event ชุดหนึ่ง ขาออกมีแค่ handoff | **ไม่ปิดประตู** — โมเดลขาออกเป็น event-carrying เชิงแนวคิด (handoff = event แรก, `cancel` ตามได้) | v1 ทำ handoff-out + inbound events; `cancel` เพิ่มภายหลัง (ความสมมาตรในเอกสารไม่มีต้นทุน) |
| 3 | **ร.พ. ที่ไม่มีหลังบ้านเลย** (OPD ล้วน) | **ไม่มีรู** | — | handoff **optional ต่อ service**: ไม่มี registered handler = NudDee เดิน journey เองทั้งเส้น (= คำตอบของ ร.พ. อื่นที่ไม่มี telemed) |

**รูปแบบที่สำคัญ:** เคส 1 และ 2 เจอรู แต่ข้อสรุปเหมือนกัน — **ซองไม่ต้องแก้ ฟีเจอร์ไม่ต้องสร้าง** แค่ยืนยันว่าซองไม่ปิดประตู นี่คือ "ยืดหยุ่นสุดเท่าที่ไม่พัง" แบบพิสูจน์ได้ ไม่ใช่แบบเดา

**บททดสอบว่า generic พอจริง:** contract ต้อง render ได้ทั้ง **Telemed** (หลายสเต็ป, ส่ง Meet link ผ่าน `ready`, จบด้วยวินิจฉัยเสร็จ) **และ OPD ที่ไม่มีหลังบ้านเลย** (NudDee เดินเองทั้งเส้น ไม่มี handoff) ด้วย**รูปเดียว** ถ้าครอบทั้งกรณีรวยสุด/จนสุด/ไม่มีหลังบ้านได้ = ถูก

---

## 7. Deferred — generic ผิดวิธีจะลากของพวกนี้เข้ามา (ห้ามทำตอนนี้)

- self-serve developer portal / app registration UI
- full webhook bus + DLQ dashboard (minimal RQ retry/dead-letter พอ)
- changes-feed / delta polling (`changes-since` cursor)
- **bidirectional clinical sync — never**
- CSV / FHIR transport (JSON อย่างเดียว; แต่ blob เปิดของ `context`/`payload` ไม่ปิดประตู FHIR)
- cross-tenant identity (identity scope ที่ระดับ tenant ก่อน; เผื่อ seam ไว้; cross-tenant = ระเบิด PDPA)
- workflow engine สำหรับ `next` directive (vocab จิ๋ว ๆ พอ)

ทั้งหมดนี้รอ **demand จริง** ดึงออกมา

---

## 8. ลำดับเมื่อถึงเวลา build (หลัง demand pull)

**prerequisite (มีแล้ว):** identity contract นิ่ง (§4.6.1) + Phase 4 notify path (`channel_links` + `notify_service`) ใช้งานได้ — commit `9151965`

**v1 (ลูกค้าแรก, 1 handler 1 service เช่น Telemed):**
1. `handoff` outbound + RQ retry/dead-letter
2. inbound events endpoint: `accepted` / `ready` / `completed` / `failed`
3. `patient_payload` renderer type `link` (ส่ง Meet link ผ่าน notify path เดิม)
4. registration 1 row + API key ผูก tenant + audit log

**ไม่แตะใน v1:** `cancel`, `status` (optional), ของในรายการ §7

**บททดสอบรับงาน:** ซองเดียว render ได้ทั้ง Telemed เต็มสตรีม + OPD ที่ไม่มีหลังบ้าน

---

## 9. Decisions Log

### Patch 20 มิ.ย. 2026 — แยก Platform Integration เป็นเอกสาร (design ล็อก, build deferred)

ตัดสินร่วมกับเจ้าของโปรเจกต์ — **อย่า re-litigate:**

- **positioning:** NudDee = ประตูหน้าบ้าน (front door); handler = หลังบ้านเฉพาะทาง (สอดคล้อง decision #2 main plan) — **ล็อกแล้ว**
- **กลยุทธ์ขาย:** ขาย front door ผ่านบริการเชื่อมง่ายก่อน (OPD/ทันตกรรม) สะสมคนไข้บน LINE OA ของ ร.พ. → Telemed ดูดเข้ามาเป็น integration ทีหลังตอนอำนาจต่อรองอยู่ข้างเรา; **โน้มน้าวที่ ร.พ. ไม่ใช่เจ้าของ Telemed** — การเลิก LINE entry ของ Telemed = "นโยบาย one-entry ของ ร.พ." ไม่ใช่เราไปขอ
- **LINE OA เป็นของ ร.พ. (NudDee operate ให้)** ไม่ใช่ของ NudDee — กัน lock-in fear ตอนปิดดีลแรก; switching cost มาจาก integration + identity graph ที่เรา operate ไม่ใช่จับ OA เป็นตัวประกัน
- **contract = 3 ข้อความ** (`handoff` / `lifecycle event` / `patient_payload`); **ซองล็อก** (§4), **ไส้ในทึบ** (§5)
- **`external_ref` opaque แยกจาก `patient_ref`** (กัน PII รั่ว); **API key ผูก tenant, resolve schema จาก key เท่านั้น** (กัน cross-tenant breach)
- **handoff optional ต่อ service** (ไม่มี handler = NudDee เดินเอง) — รองรับ ร.พ. ที่ไม่มีหลังบ้าน
- **identity scope ที่ tenant ก่อน;** cross-tenant = deferred (PDPA)
- **bidirectional clinical sync = never;** ผลคลินิกไม่ไหลกลับมาเก็บ (PDPA data minimization)
- **build deferred** จนมี demand จริง — ล็อกเฉพาะ design/ซองตอนนี้ (รูปแบบเดียวกับ AI/ML roadmap เป็น Phase 5+)

---

*จบเอกสาร — design ล็อกแล้ว, รอ demand ดึง build; เริ่มที่ §8 v1 เมื่อถึงเวลา*
