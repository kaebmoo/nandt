# NudDee Flask Migration Plan

> **Goal:** bring every user-facing template in `flask_app/app/templates/` into pixel-alignment with this design system — without breaking anything.
>
> **User's hard rule:** *"ถ้าเปลี่ยนแล้วมีปัญหากับการทำงานของโปรแกรม ไม่ควรทำ"* — if a change risks breaking the program, don't do it.

## Scope

**In scope:**
- `flask_app/app/templates/**/*.html` — Jinja templates (landing, booking flow, auth, tenant dashboard, settings)
- `flask_app/app/static/css/*.css` — custom CSS (very little — codebase uses Tailwind CDN utilities directly)
- `flask_app/app/static/` — logo/image assets
- Email templates if they live under `flask_app/app/templates/email/`

**Out of scope (do not touch):**
- `fastapi_app/` — no UI
- `admin_app/` — Bootstrap, intentionally different
- `flask_app/app/routes/` — backend logic
- `flask_app/app/models/` — database
- `flask_app/app/forms.py` / Flask-WTF form classes
- Migrations (`alembic/` or equivalent)
- Any `__init__.py`, config, env files

## Phase 0 — Audit (do this first, commit as `MIGRATION_AUDIT.md`)

Walk every `.html` under `flask_app/app/templates/`. For each, answer:

| Column | Notes |
|---|---|
| Path | e.g. `public/booking_flow/date_time.html` |
| User surface | Patient, hospital admin, marketing visitor |
| Current state | "matches design system" / "needs visual pass" / "needs structural refactor" |
| Jinja complexity | Number of `{% block %}`, macros, inherited templates |
| Risk flags | Calls `csrf_token()`? Uses form rendering? Dynamic JS? |
| Target component | Reference into `ui_kits/booking/` (e.g. `DateTimePicker.jsx`) |
| Priority | P0 public booking · P1 landing · P2 auth · P3 tenant dashboard · P4 settings · P5 emails |

**Deliverable:** commit `MIGRATION_AUDIT.md` at `hospital-booking/` root. Nothing else changes in this commit. Get the audit merged/reviewed before Phase 1.

## Phase 1 — Public booking flow (highest impact, every patient sees it)

Target templates (typical structure — verify against real paths):

| Template | UI kit ref | Key changes to expect |
|---|---|---|
| `public/booking_flow/event_types.html` | `EventTypes.jsx` | Card grid · hover lift · purple→blue gradient CTA · colored top bar per event |
| `public/booking_flow/date_time.html` | `DateTimePicker.jsx` | Stepper component · calendar day states · time-slot grid · sticky summary |
| `public/booking_flow/customer_form.html` | `BookingForm.jsx` | Field labels · focus ring · info banner · sticky summary aside |
| `public/booking_flow/success.html` | `BookingSuccess.jsx` | Green check circle · booking-reference monospace · info banner · add-to-calendar |
| `public/booking_flow/_stepper.html` (new macro) | `Stepper` subcomponent of `DateTimePicker.jsx` | Lift into a reusable Jinja macro |

**Rules for this phase:**
- Each template is one commit
- `flask run` → open page → eyeball → commit → next
- Any time you touch a form field, DO NOT rename the `name=` attribute — it must match Flask-WTF

## Phase 2 — Landing

| Template | UI kit ref | Notes |
|---|---|---|
| `marketing/index.html` (or whatever the landing is) | `Landing.jsx` | Hero gradient `#667eea → #764ba2` · 3-up features · pricing grid with popular ribbon |

The hero gradient is the ONE custom color pair in the system. Inline-style it, don't add to Tailwind config.

## Phase 3 — Auth

Templates typically live in `auth/login.html`, `auth/signup.html`, `auth/forgot.html`. Visual vocabulary:

- Centered card, `max-w-md mx-auto`, `bg-white rounded-xl shadow-md p-8`
- NudDee logo at top (lightning bolt + wordmark, `w-10 h-10` + `text-2xl font-bold`)
- Purple primary CTA
- `text-purple-600 hover:underline` for "ลืมรหัสผ่าน?" link

## Phase 4 — Tenant dashboard

The tenant dashboard is the hospital-admin surface. Key components it likely needs:

- Navbar with hospital name + user dropdown (see `Chrome.jsx::Navbar`)
- Sidebar or tabs (NOT in ui_kits yet — if encountered, propose a design before building)
- Data tables for bookings
- Empty states (use the tone/copy from README)

**If you encounter a dashboard component that isn't in `ui_kits/booking/`:**
Stop. Flag it. Ask the product owner whether to (a) copy the existing visual as-is with only cosmetic cleanup, or (b) pause and let the design system author add a new component.

## Phase 5 — Settings

Event types, availability, holidays, providers. These are CRUD screens — mostly forms. Use `BookingForm.jsx` as the field-styling reference.

## Phase 6 — Emails

Email templates are HTML too, but have stricter rules:
- **No external CSS.** Inline `style=""` only. No Tailwind CDN (won't render in mail clients).
- **No SVG icons in Gmail/Outlook.** Use emoji from the sanctioned set, or a tiny inline `<img>` with a hex fallback.
- **Use a 600px-wide table layout**, not Flexbox or Grid.

Before migrating emails, run a test send to Gmail + Outlook. If they look wrong, fix and re-send. Don't merge email template changes without this.

## Safe-first reminders (repeat for each commit)

1. ✅ Template still renders without a 500
2. ✅ Form submissions still succeed (if form was touched)
3. ✅ CSRF token is still present
4. ✅ No Jinja variables disappeared
5. ✅ Thai strings are preserved verbatim (visuals only — no copy rewrite without approval)
6. ✅ One page per commit
7. ✅ Commit message references the template path and the ui_kit ref

## Escalations — stop and ask

Stop and message the user (do not silently proceed) if you encounter:

- A template that uses inline JavaScript doing DOM manipulation the visual change would break
- A template that extends from a base you haven't audited
- A form that renders via a macro you don't recognize
- A route that seems to render multiple templates conditionally
- Any non-English non-Thai string (sign of a third locale — confirm i18n strategy first)
- A template with tests that assert on specific HTML structure
