# NudDee SaaS — AI/ML Roadmap (Phase 5+)

> **เอกสารนี้คืออะไร:** roadmap + implementation spec สำหรับนำ AI/ML เข้ามาในระบบคิว/นัด/ข้อความ แบบ "คุมต้นทุน token เป็นอันดับแรก" — ละเอียดพอให้ลงมือ code ต่อได้โดยไม่ต้องเดา
> **ความสัมพันธ์กับแผนหลัก:** เอกสารเสริมของ [`NudDee_Queue_and_Messaging_Implementation_Plan.md`](./NudDee_Queue_and_Messaging_Implementation_Plan.md) — ไม่แทนที่ และไม่ re-litigate decision ที่ล็อกแล้ว (อ้างถึง §/decision ของแผนหลักตลอด)
> **สถานะ:** Phase 4 (notification + identity contract + called-timeout) เสร็จแล้ว (commit `9151965`, 144 passed) → **Track A/B เริ่มได้เลย**; AI ยังไม่เริ่ม implement
> **กฎเหล็ก:** งานทำนายทุกตัวเป็น local ML รันใน Python ฝั่งเรา (ต้นทุนต่อครั้ง = 0 token); LLM ใช้เฉพาะงานที่ต้องตีความภาษาคน (assistant, insight) ภายใต้ tiered routing

---

## 0. หลักการคุมต้นทุน (อ่านก่อนทุก track — ห้ามข้าม)

กฎเหล่านี้กำหนดสถาปัตยกรรมของทุก AI feature เหมือนที่ §0.5 ของแผนหลักกำหนดสถาปัตยกรรมการแจ้งเตือน

0.1 **Local ML ก่อนเสมอ (0 token).** service-time, no-show เป็น tabular ML / heuristic รันใน Python ไม่เรียก LLM. LLM เฉพาะ assistant/insight

0.2 **Tiered routing สำหรับงานที่แตะ LLM.** ปุ่ม/regex → DB lookup ก่อนเสมอ → classifier เล็ก (Haiku) เฉพาะ free-text กำกวม → model ใหญ่ (Sonnet) เฉพาะตอนสังเคราะห์จริง. เป้า traffic ~80% ไม่แตะ LLM

0.3 **Heuristic-first, ML เมื่อข้อมูลพอ (YAGNI).** ทุก track เริ่มด้วย rule ที่อธิบายได้ แล้วค่อยอัปเป็นโมเดลเมื่อมี label/sample พอ — ไม่ train บนข้อมูลว่าง

0.4 **Batch ไม่ stream สำหรับ analytics.** insight/รายงาน = batch (เช่น 1 call/สัปดาห์/tenant)

0.5 **Template ไม่เรียก LLM ตอน runtime.** notification ใช้ template + variable เด็ดขาด; ถ้าอยากได้ถ้อยคำสวยให้ LLM ช่วยร่าง template ตอน dev ครั้งเดียว

0.6 **Structured/constrained output แทน open generation.** classification ให้ map → 1 ใน N ค่าที่กำหนด

0.7 **AI ต้องไม่แทน deterministic core.** wait estimator core, notification dispatch, grace/starvation guard — deterministic ที่ดีและถูกอยู่แล้ว ห้ามเอา LLM ไปแทน

0.8 **AI ทุกตัวขับด้วย per-tenant config (decision #8 แผนหลัก).** ทุก feature มี flag เปิด/ปิด + พารามิเตอร์ต่อ tenant; default ต้อง "ปิดผล" (no-op) เพื่อ backward-compat

0.9 **LLM provider boundary (Track C/D) — เพิ่ม 21 มิ.ย. 2026.** ข้อความที่คนไข้พิมพ์เอง (feedback ของ Track C, free-text ของ Track D) อาจมี PII → LLM provider เป็น strategy seam per-tenant `llm_provider` = `none | self_hosted | external`, **default `none` (ปิด)**. เมื่อเปิด default ที่แนะนำคือ **`self_hosted`** (Typhoon/SeaLLM — PII ไม่ออกนอกขอบเขตที่เราคุม, เข้ากับ PDPA consent-based + data-minimization §4/§5 Platform plan); **`external`** (Haiku/Sonnet) เป็น **opt-in เฉพาะ tenant ที่มี consent + DPA ครบ** — ไม่ปิดประตูแต่ไม่ใช่ default. งานทำนาย (Track A/B) = local ML 0 token ไม่แตะข้อนี้; Track D ส่วนใหญ่หยุดที่ T0/T1 (0 token) ไม่ถึง LLM อยู่แล้ว

---

## 1. Seam ที่มีอยู่แล้ว (architecture รองรับ — ไม่ต้อง refactor)

จาก audit codebase โครงสร้างถูกวางเผื่อ AI ไว้แล้ว เสียบได้โดยไม่แตะ caller/template:

| AI track | จุดเสียบจริงในโค้ด | สถานะ seam |
|---|---|---|
| Service-time learning | `services/estimation/base.py` → `get_estimator()` factory + `WaitEstimator` Protocol + `EstimateResult.method/confidence`; `simple_avg.rolling_service_time()` | พร้อม (comment ระบุ "future Erlang-C/ML estimators") |
| No-show / scoring | `services/priority_service.py` → `compute_priority_score()` + `mode='score'` + `QueuePolicy.w_class/w_wait/w_window` | score mode implement แล้ว (default `ratio`) |
| Insight / dashboard | `services/analytics_service.py` → `queue_summary()` (no_show_rate, avg_wait/service, hourly_checkins, class_counts), `message_cost_summary()` | พร้อมเป็น feature store + cost tracker |
| Conversational assistant | `webhook_routes.py` → `_START_SERVICE_POINT_RE` (regex command), `_post_telegram_message(reply_markup=...)`, `extract_patient_ref` | tier 0/1 มีโครงแล้ว เหลือชั้น fallback |

**ข้อสรุป:** ไม่มี track ไหนต้อง refactor — เป็นการ "เสียบ" เข้า seam ที่มี หรือ "ต่อท้าย" analytics

---

## 2. AI Tracks (implementation spec)

เรียงตามความคุ้ม + dependency — ทำตามลำดับ A → B → C/D

---

### Track A — Service-time learning (estimator) — ต้นทุน: 0 token

**A.1 ปัญหาปัจจุบัน**
`rolling_service_time()` คิด p80 ต่อ `service_point` เดียว รวมทุกชนิดบริการ → บริการที่เวลาต่างกันมาก (ตรวจ 5 นาที vs หัตถการ 30 นาที) ถูกเฉลี่ยรวม → estimate เพี้ยน

**A.2 เป้าหมาย** service time แยกตาม `(service_point, event_type[, ช่วงเวลา])` → wait แม่นขึ้น โดยไม่แตะ caller

**A.3 Contract (caller ไม่แก้)**
```
# flask_app/app/services/estimation/learned_avg.py (สร้างใหม่)
class LearnedServiceEstimator:
    def __init__(self, db, tenant_config=None): ...
    def estimate(self, entry, now=None) -> EstimateResult:
        # คืน EstimateResult(method='learned_p80', confidence='approx'|'low')
        # confidence='low' เมื่อ sample < min_samples (fallback)
```
- `get_estimator()` เลือก strategy จาก `tenant_config['estimator_strategy']` (default `'simple_avg'`)
- คืน `EstimateResult` เดิม → queue route/template/`count_ahead` caller ไม่ต้องแก้

**A.4 Algorithm (ไต่ระดับ — ทำ Lv2.5 ก่อน)**
- **Lv2.5** เพิ่ม helper `rolling_service_time(db, service_point_id, event_type_id=None, ...)` (ขยายของเดิมให้รับ event_type optional): กรอง `done` entries + join `appointment.event_type_id`. ถ้า sample < `min_samples` → fallback service_point-level → ถ้ายังไม่พอ → `DEFAULT_SERVICE_MINUTES`. entry ที่ทำนาย: ดู event_type จาก appointment (walk-in ไม่มี → ใช้ service_point-level)
- **Lv3** class-aware `people_ahead` (patch B แผนหลัก): `count_ahead` ปัจจุบันนับตาม `queue_number` ดิบ (positional) → under-estimate walk-in. แก้ให้นับตาม effective priority order (ดู `priority_service._select`) ผ่าน factory เดียวกัน
- **Lv4 (optional)** offline quantile regression: feature = (event_type, hour_bucket, people_ahead); train batch แล้ว cache coefficient; estimator แค่ lookup+apply (ยัง 0 token)

**A.5 Schema**
- Lv2.5/Lv3 — ไม่ต้องเพิ่ม table (ใช้ aggregate query สด บน field ที่มี: `service_start_at/service_end_at`)
- Lv4 — table cache `service_time_models(service_point_id, event_type_id, hour_bucket, coef..., updated_at)` ต่อ tenant schema

**A.6 Config (per-tenant)** `estimator_strategy` (default `'simple_avg'`), `service_time_min_samples` (default 8), `service_time_lookback_days` (default 30) — เก็บที่เดียวกับ tenant_config ที่ส่งเข้า `get_estimator()`

**A.7 Files** create `estimation/learned_avg.py`; modify `estimation/base.py` (get_estimator เลือก strategy), `estimation/simple_avg.py` (refactor rolling_service_time รับ event_type); extend `tests/test_estimation_service.py`

**A.8 Acceptance**
- บริการ 2 ชนิดเวลาต่างกัน → estimate ต่างกันสมเหตุผล
- sample < threshold → fallback ไม่ error, `confidence='low'`
- ไม่มี done entry → `DEFAULT_SERVICE_MINUTES`
- queue route ไม่ต้องแก้แม้แต่บรรทัดเดียว (ยืนยันด้วย test เดิมยังเขียว)

---

### Track B — No-show prediction — ต้นทุน: 0 token (local ML)

**B.1 การใช้ output (3 ทาง)**
1. **reminder targeting** — ส่งเตือนซ้ำเฉพาะ risk สูง → ลด push เสียเงิน (สอดคล้อง §0.5 แผนหลัก)
2. **priority score** — เพิ่ม term `w_noshow * risk` ใน `compute_priority_score` (เผื่อ overbook)
3. **overbook suggestion** — admin เห็นช่วงเสี่ยงว่าง → เปิดรับเพิ่ม (human-confirm)

**B.2 Prerequisite — พร้อมแล้ว (commit `9151965`)**
- identity contract (§4.6.1) เสร็จ: ใช้ `identity_service.resolve_patient_ref(*, appointment=..., patient=..., phone=...)` → canonical `patient:{id}` | `phone:{normalized_phone}` | `anon:{token}` (precedence: patient_id ก่อน phone ก่อน anon; ชื่อไม่เป็น key) เพื่อรวมนัดของคนเดียวกัน
  - **หมายเหตุ (เพิ่ม 21 มิ.ย. 2026):** `anon:{token}` เป็น technical fallback ของ walk-in ที่ไม่ระบุตัวตน → ไม่มี no-show history ให้รวม → **Track B ข้าม entry ที่ ref เป็น `anon:` (risk=0)**; no-show พึ่ง `patient:{id}`/`phone:` ที่มี history เท่านั้น
- `notification_log` (Phase 4) พร้อมสำหรับวัดผล reminder; identity gate (`no_linked_identity`) ใน `notify_service` คุมกฎ §10 ให้แล้ว

**B.3 Feature set (จาก field จริง — ไม่ต้องเก็บใหม่)**
| feature | ที่มา |
|---|---|
| prior_no_show_count / prior_total | นับ `QueueEntry.status='no_show'` ต่อ patient_ref ที่ได้จาก `resolve_patient_ref(appointment=...)` (lookback) |
| prior_no_show_rate | count / total |
| lead_time_days | `appointment.created_at` → `appointment.start_time` |
| appointment_hour, weekday | `appointment.start_time` |
| event_type_id | `appointment.event_type` |
| is_first_visit | prior_total == 0 |

**B.4 Algorithm (heuristic-first → ML)**
- **B1 (heuristic, 0 train):** banded rule → risk 0..1 เช่น `prior_no_show_rate >= 0.5` (มี history ≥ 2) หรือ `is_first_visit AND lead_time_days > 21` → high; กำหนด band → score
- **B2 (ML):** logistic regression / LightGBM, train offline (RQ nightly), persist coefficient ต่อ tenant; inference เป็น pure Python (0 token). ถ้า terminal-appointment label < `min_labels` → ใช้ heuristic ต่อ

**B.5 Service contract**
```
# flask_app/app/services/noshow_service.py (สร้างใหม่)
def predict_risk(db, appointment) -> float          # 0..1
def risk_band(score: float) -> str                  # 'low'|'med'|'high'
def high_risk_appointments(db, date_from, date_to)  # reminder targeting + dashboard
```
- batch nightly ใน `flask_app/app/tasks.py` (compute on-demand ได้ ไม่ต้อง cache ถ้า volume ต่ำ)

**B.6 Schema**
- เพิ่ม `QueuePolicy.w_noshow FLOAT DEFAULT 0` — migration `migrations/add_queue_policy_w_noshow.py` (idempotent + backfill 0). **default 0 = ปิดผลต่อ score** จนกว่าจะเปิด (backward-compat)
- `compute_priority_score` เพิ่ม term `+ float(policy.w_noshow) * noshow_risk` (เฉพาะ appointment; walk-in risk=0)
- config per-tenant: `noshow_enabled` (default False), `noshow_reminder_threshold` (default 'high')
- (B2 only) table `noshow_models` เก็บ coefficient ต่อ tenant

**B.7 Boundary (สำคัญ — กัน regress decision ที่ล็อก)**
- no-show **เสริม** score เท่านั้น — starvation guard + grace ยังเป็น hard override ก่อน score (คงพฤติกรรม `priority_service._select` ปัจจุบัน: starving check มาก่อน score)
- overbook **ไม่อัตโนมัติ** — suggestion + human-confirm + per-tenant toggle
- reminder ยังผ่านกฎ §10: push เฉพาะ patient_ref + `channel_links` active เท่านั้น

**B.8 Files** create `services/noshow_service.py`, `tests/test_noshow_service.py`, migration w_noshow; modify `priority_service.compute_priority_score` (+term, w_noshow=0 → no-op), `appointment_notifications.py` (targeting), `tasks.py` (batch)

**B.9 Acceptance**
- `w_noshow=0` → score เท่าเดิมเป๊ะ (test priority เดิมยังเขียว — ไม่ regress decision #5/#6)
- heuristic ทำงานโดยไม่มี trained model
- reminder targeting: push ใน `notification_log` ลดลงเทียบส่งทุกคน
- patient ไม่มี `channel_links` → ไม่ push (pull/log)

---

### Track C — Feedback / complaint insight — ต้นทุน: LLM batch (ต่ำมาก)

**C.1 เป้าหมาย** สรุปเทรนด์ความเห็น/ร้องเรียนต่อ tenant รายสัปดาห์ เป็น insight เชิง ops

**C.2 Prerequisite** ต้องมีที่เก็บ feedback (ยังไม่มีในระบบ) → ถ้ายังไม่มี demand จริง = **YAGNI ข้ามไปก่อน** อย่าสร้าง channel ลอย ๆ

**C.3 ถ้าทำ**
- table `feedback(rating, comment, created_at, event_type_id?)` ต่อ tenant schema
- batch 1 call/สัปดาห์/tenant: input = comment aggregate, output = **structured JSON** (หมวด, ความถี่, ตัวอย่างย่อ, เทรนด์เทียบสัปดาห์ก่อน)
- model: Haiku พอ (งานสรุป ไม่ต้อง Sonnet)

**C.4 Boundary** ops insight ไม่ใช่ medical advice; constrained/structured output

**C.5 Files** migration feedback table, `services/feedback_insight_service.py`, batch ใน `tasks.py`, dashboard partial (ต่อ analytics §3.3 แผนหลัก)

---

### Track D — Conversational assistant (LINE/Telegram) — ต้นทุน: LLM tiered (คุมเข้ม)

**D.1 เป้าหมาย** ตอบ free-text บนแชตที่ปุ่ม/regex เดิมไม่ครอบคลุม โดยให้ traffic ส่วนใหญ่ไม่แตะ LLM

**D.2 Gateway ที่มีแล้ว** `webhook_bp` (`/webhooks`), `_START_SERVICE_POINT_RE` (regex command), `_post_telegram_message(reply_markup=...)` (ปุ่ม), `extract_patient_ref`, `verify_line_signature` / `validate_telegram_init_data`

**D.3 Tiered routing (บังคับ)**
| tier | ทำอะไร | token |
|---|---|---|
| T0 | Rich Menu / quick reply / ปุ่ม → action เด็ดขาด (คิว/เลื่อน/ยกเลิก) | 0 |
| T1 | regex (ขยายจาก `_START_SERVICE_POINT_RE`) จับ intent ตรง → DB | 0 |
| T2 | intent classifier (Haiku, constrained output → 1 ใน N intent) เฉพาะ free-text ที่ T0/T1 ไม่จับ | ต่ำ |
| T3 | Sonnet เฉพาะต้องสังเคราะห์/ตอบความรู้ซับซ้อน | สูง (ใช้น้อยสุด) |

เป้า ~80% traffic หยุดที่ T0/T1 (0 token)

**D.4 ต้นทุนช่องทาง (สอดคล้อง §0.5 แผนหลัก)** ตอบใน reply-token context (sync ใน webhook) = ฟรีฝั่ง LINE; Telegram ฟรีเสมอ; **ตัว LLM ยังมีค่า token ฝั่งเรา** → คุมด้วย tier. reply token ใช้ได้เฉพาะ webhook context → **อย่าออกแบบ assistant async ผ่าน LINE** (async = push เสียเงินเท่านั้น)

**D.5 Boundary (สำคัญ)**
- triage = "แนะนำแผนก/ความเร่งด่วน" ไม่ใช่ "วินิจฉัย" + disclaimer + human-in-loop (liability ทางการแพทย์ไทย)
- assistant **ห้ามทำ side-effect** (cancel/reschedule/ออกคิว) โดยไม่ยืนยัน — ให้ classifier เด้งกลับ flow เดิมที่มี confirm step ไม่ให้ LLM เรียก mutation ตรง
- ห้าม LLM generate notification template ตอน runtime (§0.5)

**D.6 ขั้นพัฒนา** ขยาย T0/T1 ให้ครอบคลุมก่อน (0 token) → เพิ่ม T2 fallback → T3 ท้ายสุด

**D.7 Files** modify `webhook_routes.py` (เพิ่ม fallback chain หลัง regex), create `services/assistant_router.py` (intent classify + dispatch กลับ flow เดิม), tests

**D.8 Acceptance** intent ที่ครอบด้วยปุ่ม/regex → ไม่เรียก LLM (วัดด้วย counter); assistant ไม่ทำ mutation โดยไม่ confirm; triage มี disclaimer เสมอ

---

### ภาคผนวก — Demand smoothing (ไม่ใช่ AI แต่เกี่ยวข้อง)

ตอนจอง แนะนำช่วงเวลาที่ว่างกว่าเพื่อเกลี่ยโหลด — แค่ query + heuristic บน availability/session ที่มี ไม่ใช้ AI ไม่กิน token ลดคิวกระจุก ทำได้ทุกเมื่อ ไม่ต้องรอ track อื่น

---

## 3. ลำดับ implement + dependency

```
Phase 4 (notification + identity contract + called-timeout)   — DONE (commit 9151965, 144 passed)
        │
        ├── Track A (service-time learning)   ← เริ่มได้ทันทีหลัง Phase 4 (ไม่พึ่ง identity)
        │
        └── identity contract พร้อม
                  │
                  └── Track B (no-show)        ← พึ่ง patient_ref history
                            │
                            └── Track C / D (LLM: insight / assistant)  ← ทำท้ายสุด
```

- **A** พึ่งแค่ข้อมูล service time (มีแล้ว) → เริ่มได้เลย
- **B** พึ่ง identity contract — **พร้อมแล้ว** (`identity_service.resolve_patient_ref` + `notification_log` จาก Phase 4) → เริ่มได้เลย
- **C/D** เป็น LLM → ทำหลังสุด เมื่อ flow deterministic นิ่ง
- **Demand smoothing** อิสระ ทำได้ทุกเมื่อ

---

## 4. กฎ "ห้ามทำ" (cost / safety — ต่อยอด §10 แผนหลัก)

- ห้ามเอา LLM แทน wait estimator core / notification dispatch / grace-starvation guard
- ห้ามส่งข้อความที่คนไข้พิมพ์เอง (feedback/assistant free-text) ไป external LLM เว้นแต่ tenant ตั้ง `llm_provider='external'` + มี consent + DPA ครบ (ดู §0.9) — default `none`/`self_hosted` (PII ไม่ออกนอกขอบเขต)
- ห้ามเรียก LLM ต่อข้อความ notification (template + variable เท่านั้น)
- ห้าม train model บนข้อมูลว่าง — heuristic-first จนกว่า sample/label พอ
- ห้ามให้ assistant ทำ side-effect โดยไม่ยืนยันกับผู้ใช้
- ห้ามทำ triage เป็น "วินิจฉัย" — เป็น "แนะนำแผนก" + disclaimer เท่านั้น
- ห้ามให้ no-show override decision ที่ล็อก (grace/starvation/priority) — เป็น weight เสริมที่ default = 0
- ห้าม push หา patient ที่ยังไม่มี `patient_ref` + `channel_links` active (กฎเดิม §10 — ใช้กับ no-show reminder ด้วย)
- ห้าม estimator/score ใหม่เปลี่ยน contract ของ caller — ต้องคืน `EstimateResult` / score เดิม; default config ต้อง no-op

---

## 5. Decisions Log

- **20 มิ.ย. 2026 — DONE:** เพิ่ม entry "AI/ML scope แยกเป็น roadmap (Phase 5+)" ลง §12 ของแผนหลักแล้ว (Patch 20 มิ.ย. 2026); ปรับ §1.4 (ระบุ score mode implement แล้ว + link roadmap) และ decision #5 (สถานะ score mode + พา no-show เข้า `w_noshow`)
- **20 มิ.ย. 2026 — Phase 4 เสร็จ:** notification (4.1/4.13) + identity (A) + called-timeout (D) wired แล้ว (commit `9151965`, 144 passed) → prerequisite ของ Track A + B met, เริ่ม implement ได้
- **ล็อก:** AI/ML = Phase 5+; งานทำนาย = local 0 token; LLM เฉพาะ assistant/insight ใต้ tiered routing; no-show เสริม score (default `w_noshow=0`) ไม่ override grace/starvation; ลำดับ A → B → C/D
- **21 มิ.ย. 2026 — ล็อก LLM provider boundary:** `llm_provider` per-tenant `none|self_hosted|external`, default `none`; เปิด = แนะนำ `self_hosted` (PII ไม่ออกนอกขอบเขต), `external` opt-in เฉพาะมี consent+DPA — ไม่ปิดประตูแต่ไม่ใช่ default (ดู §0.9 + §4)

---

## 6. Link เข้าแผนหลัก — DONE (20 มิ.ย. 2026)

- §1.4 (Current State): เพิ่มบรรทัด score mode + AI/ML upgrade path ชี้มาที่ไฟล์นี้
- decision #5: เติมสถานะ `mode='score'` + ทางเข้า `w_noshow` (Track B)
- §12 Decisions Log: เพิ่ม Patch 20 มิ.ย. 2026 (scope/cost/boundary/ลำดับ/seam)

> back-link จาก roadmap → แผนหลัก ใช้ §-reference ในแต่ละ track อยู่แล้ว (§4.6.1, §5.4, §5.5, §10, decision #5/#6/#8)
