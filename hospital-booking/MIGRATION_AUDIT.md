# NudDee Flask Template Migration — Audit (Phase 0)

> **Scope:** every `.html` under `flask_app/app/templates/` (37 total).
> **Goal:** classify each template for a **visuals-only** Tailwind/Jinja migration aligned to `.claude/skills/nuddee-design/`. No JSX rewrite, no backend changes.
> **Hard rule:** ถ้าเปลี่ยนแล้วมีปัญหากับการทำงานของโปรแกรม ไม่ควรทำ — if a change risks breaking the app, don't do it.

---

## i18n sanity check

`grep -r "Flask-Babel\|flask_babel\|gettext\|_('" flask_app/` → **zero matches**.
Thai strings are hardcoded Jinja literals. Safe to keep inline during migration. **No i18n work required in scope.**

---

## Chrome & infrastructure templates (migrate carefully — shared surfaces)

| Path | User surface | Current state | Jinja complexity | Risk flags | Target component | Priority |
|---|---|---|---|---|---|---|
| `base.html` | all | matches design system (shell only) | root layout, 4 blocks (`title`, `content`, `extra_css`, `extra_js`), includes navbar/flash/footer partials, sets Sarabun + Tailwind CDN | inline global JS (`window.utils`, csrf meta) — **touch with care**, no CSRF form but defines `window.csrfToken` | shell, no 1:1 kit ref | Chrome |
| `partials/navbar.html` | Tenant user (auth branch) / Guest | needs visual pass | no extends, uses `get_nav_params()`, `get_current_user()`, `url()` helper | `url_for('auth.logout')` fallback, 🚪 emoji to replace with Heroicon, Thai menu labels | `Chrome.jsx::Navbar` | Chrome (P3-adjacent) |
| `partials/footer.html` | all | matches design system (light footer) | no extends, static | — | `Chrome.jsx::Footer` (simplified) | Chrome |
| `partials/flash_messages.html` | all | needs minor visual pass (border-l-4 vs skill's uniform border) | no extends, inline `<script>` auto-hide, 4 category branches with inline SVG | inline JS DOM (`#flash-messages-container`) — keep script; only restyle markup | `ui.jsx::Alert` | Chrome |
| `macros/forms.html` | reused macro | matches design system | 4 macros (`render_field`, `render_field_errors`, `render_checkbox`, `render_form_errors`) using Flask-WTF | all settings forms depend on these macros — structural changes here cascade everywhere | `ui.jsx::Field` | Chrome |

**Do NOT touch `base.html` inline JS or the navbar's `{{ url(...) }}` helper calls. Reskin HTML only.**

---

## Public booking flow — P0 (every patient sees it)

| Path | User surface | Current state | Jinja complexity | Risk flags | Target component | Priority |
|---|---|---|---|---|---|---|
| `booking/home.html` | Patient public | matches design system (light) | extends `base.html`, 1 `content` block, simple card loop over `event_types` | `onclick` handlers for navigation (no CSRF) | `EventTypes.jsx` | P0 |
| `booking/select_time.html` | Patient public | needs structural refactor | **no extends** (standalone page), heavy inline JS calendar + slot fetch | `csrf_token`, fetch `/api/availability`, element IDs (`calendar-day`, `slot-button`, `current-month`, `date-input`, `selected-date`) — JS hooks on these IDs | `DateTimePicker.jsx` | P0 |
| `booking/confirm.html` | Patient public | needs structural refactor | no extends, inline JS form validation + provider fetch | `csrf_token`, form rendering, `isSubmitting` guard, element IDs (`provider_id`, `provider-select`) | `BookingForm.jsx` | P0 |
| `booking/success.html` | Patient public | needs visual pass | no extends, inline calendar API fetch (`addToCalendar`) | no CSRF, fetch, booking-reference state in DOM | `BookingSuccess.jsx` | P0 |
| `booking/manage.html` | Patient public | minimal | no extends, simple status + cancel form | `csrf_token`, POST cancel, `onclick` confirm | `BookingForm.jsx` (summary variant) | P0 |
| `booking/reschedule.html` | Patient public | needs structural refactor | no extends, inline JS calendar + month nav + slot fetch | `csrf_token`, form rendering, fetch `/api/availability` & `/api/calendar`, element IDs (`calendar-day`, `selected-date`, `new-time-input`) | `DateTimePicker.jsx` | P0 |
| `booking/verify_otp.html` | Patient public | needs visual pass | extends base, inline countdown + resend JS | `csrf_token`, form rendering, fetch (resend), element IDs (`countdown`, `resend-btn`, `otp`) | `BookingForm.jsx` (OTP variant) | P0 |
| `booking/my_appointments.html` | Patient public | needs structural refactor | extends base, inline OTP-resend fetch + tab switch JS | `csrf_token`, form rendering, element IDs (`tab-btn-*`, `search-form`, `reference/email/phone-input`, `search-type`) | `BookingForm.jsx` | P0 |
| `booking/appointment_list.html` | Patient public | needs visual pass | extends base, conditional action links | no CSRF in main; status badges inline | `BookingForm.jsx` (list variant) | P0 |
| `booking/error.html` | Patient public | minimal (error page) | no extends | flashed messages only | `ui.jsx::Alert` + plain card | P0 |
| `public/booking.html` | **Patient public (legacy, standalone)** | needs structural refactor | **no extends** (own `<!DOCTYPE>`), 4-step booking inline JS, provider + event selection, slot picker, submit | `csrf_token` (form), fetch to FastAPI (`{{ fastapi_url }}`), element IDs galore (`currentMonth`, `selectedDuration`, `event-type-btn`, `selectedDateDisplay`, `morningSlots`, `afternoonSlots`, `eveningSlots`, `bookingForm`) | `BookingForm.jsx` + `DateTimePicker.jsx` + `EventTypes.jsx` combined | **P0 — but flag: duplicate of `booking/*` step-split flow?** |

**Escalation: `public/booking.html` appears to be a legacy monolithic version of the step-split `booking/` flow.** Both render patient-facing booking UI with different backend routing. Before migrating either, confirm which is live. Possibly deprecate one.

**New macro to extract (as planned):** `_stepper.html` in `flask_app/app/templates/macros/` mirroring `COMPONENT_MAP.md::Stepper` — consumed by `select_time.html` → `confirm.html` → `success.html`.

---

## Landing / marketing — P1

| Path | User surface | Current state | Jinja complexity | Risk flags | Target component | Priority |
|---|---|---|---|---|---|---|
| `landing.html` | Marketing visitor / logged-in user | needs visual pass | **no extends** (own `<!DOCTYPE>` + own navbar/footer/flash), hero gradient inline, pricing grid, 3-step signup modal | inline JS (`showSignupModal`, `handleSignup`, `selectPlan`, Escape keybind, `fetch('/api/register')`), element IDs (`signupModal`, `step1/2/3`, `loading`, `signupError`) — **modal JS tightly coupled to DOM structure** | `Landing.jsx` (hero, features, pricing) + `Auth.jsx` (signup modal) | P1 |

Hero `linear-gradient(135deg, #667eea 0%, #764ba2 100%)` already inlined as `.gradient-bg` — keep as inline `style=""` per skill rule ("ONE custom color pair"). Don't move to Tailwind config.

---

## Auth — P2

| Path | User surface | Current state | Jinja complexity | Risk flags | Target component | Priority |
|---|---|---|---|---|---|---|
| `auth/login.html` | Patient / Hospital admin | needs visual pass | no extends (standalone), own `<!DOCTYPE>`, standalone form | `csrf_token`, form rendering, inline `<style>` | `Auth.jsx::Login` | P2 |
| `auth/profile.html` | Hospital admin | needs structural refactor | extends base, 2 blocks (`extra_css`, `extra_js`), **3 modals** (edit profile, change password, OTP) | `csrf_token`, multiple form rendering blocks, inline JS DOM (3 modal toggles, OTP flow), element IDs (`editProfileModal`, `changePasswordModal`, `otpModal`, `otpForm`) — **high DOM coupling** | `Auth.jsx::Profile` | P2 |

**Escalation on `auth/profile.html`:** 3 modals with inline JS visibility management. Migrate the enclosing card markup; **leave modal DOM IDs untouched** so the JS keeps working. If styling one modal breaks another, stop and ask.

---

## Tenant dashboard + admin — P3

| Path | User surface | Current state | Jinja complexity | Risk flags | Target component | Priority |
|---|---|---|---|---|---|---|
| `dashboard.html` | Hospital admin | needs structural refactor | extends base, 2 blocks, tab switching JS, reveal-data fetch, conditional sections | `csrf_token`, inline JS DOM (`tab-*`, `upcoming-appointments`, `past-appointments`, `canceled-appointments`), fetch (`revealData`) | `Chrome.jsx::Navbar` + list layout — **no exact dashboard kit** | P3 |
| `appointments/admin_cancel.html` | Hospital admin | minimal | no extends, inline form | `csrf_token`, form rendering, inline confirm JS | `ui.jsx::Button/Card/Field` | P3 |
| `appointments/admin_reschedule.html` | Hospital admin | needs structural refactor | extends base, heavy fetch JS + calendar logic | `csrf_token`, form rendering, inline JS DOM (`slot-button`, `date-input`) | `DateTimePicker.jsx` + `BookingForm.jsx` | P3 |
| `appointments/view.html` | Hospital admin | minimal | no extends, inline reveal JS | `csrf_token`, inline JS (`revealData`), element IDs (`email-{id}`, `phone-{id}`) | `ui.jsx::Card` | P3 |

**Escalation on `dashboard.html`:** no matching component in `ui_kits/booking/`. Per `MIGRATION_PLAN.md` Phase 4: **stop and ask the product owner before building new dashboard components**. Minimum safe pass = cosmetic cleanup (navbar swap to skill version, match card padding, swap 🚪 to Heroicon), nothing structural.

---

## Settings / CRUD — P4

| Path | User surface | Current state | Jinja complexity | Risk flags | Target component | Priority |
|---|---|---|---|---|---|---|
| `settings/event-types.html` | Hospital admin | needs structural refactor | extends base, 1 `extra_js` block, modal JS, fetch to API | fetch (`loadEventTypes`, `loadAvailabilities`), element IDs (`eventTypeModal`, `eventTypeForm`, `eventTypeId`, `availabilitySelect`) | `EventTypes.jsx` (admin variant) + `BookingForm.jsx` | P4 |
| `settings/holidays.html` | Hospital admin | needs structural refactor | extends base, 2 blocks, modal JS, sync fetch, custom toggle CSS | `csrf_token`, form rendering, fetch (`handleSync`, `handleSaveHoliday`, `toggleHoliday`, `deleteHoliday`), custom toggle switch CSS, element IDs (`syncModal`, `holidayModal`, `holidayForm`, `yearSelect`) | no 1:1 kit — **custom** | P4 |
| `settings/availability/index.html` | Hospital admin | needs visual pass | extends base, uses `render_field`, `render_field_errors` macros, custom CSS for `.template-item.active` | form rendering via macros, click-to-activate JS | no 1:1 kit — **custom grid** | P4 |
| `settings/availability/form.html` | Hospital admin | needs structural refactor | extends base, 2 blocks, uses `render_field` + `render_checkbox` macros, dynamic day-toggle JS | uses macros, `csrf_token`, form rendering, inline JS DOM (`toggleDay`, `addTimeSlot`, `day-{index}`, `time-slots-{index}`) | `BookingForm.jsx` field-styling reference | P4 |
| `settings/providers/index.html` | Hospital admin | needs visual pass | extends base, 1 `extra_js`, inline toggle/delete forms | `csrf_token`, form rendering, `onclick` confirm | `ui.jsx::Card` grid | P4 |
| `settings/providers/form.html` | Hospital admin | needs visual pass | extends base, form for create/edit via macros | uses macros, `csrf_token`, form rendering | `BookingForm.jsx` field-styling reference | P4 |

---

## Emails — P5

| Path | User surface | Current state | Jinja complexity | Risk flags | Target component | Priority |
|---|---|---|---|---|---|---|
| `emails/otp.html` | Email recipient | minimal (email) | no extends, plain HTML | no CSRF, email rules apply (inline styles only, no Tailwind CDN, 600px table) | no 1:1 kit — **custom per skill rules** | P5 |

**Rule reminder (Phase 6 in plan):** no Tailwind CDN in email, no SVGs in Gmail/Outlook. Test-send to Gmail + Outlook before committing.

---

## Errors — P6 (low priority, minimal)

All extend `base.html` with a single `content` block and static content.

| Path | User surface | Current state | Target component | Priority |
|---|---|---|---|---|
| `errors/403.html` | Error page | minimal | plain centered card | P6 |
| `errors/404.html` | Error page | minimal | plain centered card | P6 |
| `errors/500.html` | Error page | minimal | plain centered card | P6 |
| `errors/not_found.html` | Error page | minimal (likely duplicate of 404) | plain centered card | P6 — **flag duplicate** |
| `errors/booking_disabled.html` | Error page | minimal | plain centered card + `history.back()` JS button | P6 |
| `errors/license_invalid.html` | Error page | minimal | plain centered card | P6 |
| `errors/service_unavailable.html` | Error page | minimal | plain centered card | P6 |

**Flag:** `errors/404.html` vs `errors/not_found.html` — check if both are reachable or if one is orphaned.

---

## Cross-cutting escalations (stop-and-ask list)

1. **Duplicate booking flows:** `public/booking.html` (legacy monolithic) vs `booking/*.html` (step-split). Confirm which is live before spending a migration on the wrong one.
2. **Duplicate 404 templates:** `errors/404.html` and `errors/not_found.html` — confirm routing.
3. **Dashboard has no component equivalent** in `ui_kits/booking/`. Phase 4 will need a product-owner decision before any structural work — planned cosmetic-only pass otherwise.
4. **`holidays.html` has no component equivalent** (custom toggle switch + year-picker + sync modal). Same question as dashboard.
5. **`auth/profile.html` 3-modal stack** — high DOM coupling. Visual-only pass is safe; structural refactor is not.
6. **Macro dependency chain:** `render_field`, `render_checkbox`, `render_field_errors`, `render_form_errors` in `macros/forms.html` are consumed by every settings form. If the macros are changed, every consuming template re-renders — audit together or not at all.
7. **Hardcoded API hosts in inline JS:** `settings/event-types.html` and others reference `http://localhost:8000/api/v1`. Pre-existing bug; not migration-blocking but worth a follow-up ticket.
8. **`🚪` emoji → Heroicon `arrow-right-on-rectangle`** is called out in the skill. Swap wherever logout appears (currently `partials/navbar.html` and `landing.html` dropdown).

---

## Migration order (proposed)

```
Phase 0 (this audit) → commit, stop for review
Phase 1 P0  booking/home.html → select_time.html → confirm.html → success.html
           verify_otp.html → my_appointments.html → appointment_list.html
           manage.html → reschedule.html → error.html
           extract macros/_stepper.html along the way
           (public/booking.html deferred pending dedup decision)
Phase 2 P1  landing.html
Phase 3 P2  auth/login.html → auth/profile.html (visual-only on profile)
Phase 4 P3  partials/navbar.html (🚪 → Heroicon, cosmetic polish)
           dashboard.html (cosmetic-only until product owner weighs in)
           appointments/view.html → admin_cancel.html → admin_reschedule.html
Phase 5 P4  settings/providers/index.html → providers/form.html
           settings/availability/index.html → availability/form.html
           settings/event-types.html → settings/holidays.html
Phase 6 P5  emails/otp.html (inline styles + Gmail/Outlook test)
Phase 7 P6  errors/*.html (batch-friendly since they're near-identical)
```

**One page per commit.** Each commit must render 200 + preserve CSRF + preserve form field `name=""` attributes.

---

## Stats

- **Total templates:** 37
- **Chrome/shared:** 5
- **P0 public booking:** 11 (incl. legacy `public/booking.html`)
- **P1 landing:** 1
- **P2 auth:** 2
- **P3 dashboard + admin:** 4
- **P4 settings:** 6
- **P5 emails:** 1
- **P6 errors:** 7
- **Flask-Babel / i18n:** none detected — Thai stays inline
