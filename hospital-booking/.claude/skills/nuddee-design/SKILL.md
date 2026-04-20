---
name: nuddee-design
description: Design system and UI reference for NudDee (นัดดี), a Thai-first appointment-booking SaaS. Use this skill when the user asks to design, build, audit, refactor, or modify ANY user-facing UI in the hospital-booking codebase — landing pages, booking flow, tenant dashboards, auth, settings, emails. Contains color/type tokens, content rules, iconography, and React component recreations that mirror the target visual vocabulary. Do NOT use this for FastAPI changes (no UI) or the Bootstrap Super Admin panel (intentionally different visual language).
user-invocable: true
---

# NudDee Design skill — Claude Code edition

You are working inside the `kaebmoo/nandt` repo, subtree `hospital-booking/`. The canonical brand surface is `flask_app/` (Flask + Jinja + Tailwind CDN + Sarabun). Two surfaces are explicitly OUT OF SCOPE for this skill:

- `fastapi_app/` — no UI. **Do not touch.**
- `admin_app/` — Bootstrap 5 + FontAwesome internal tool, different visual language. **Do not touch.**

## Required reading order

Before editing any template, read these files from this skill directory:

1. **`README.md`** — product context, content fundamentals, visual foundations, iconography. Ground truth for every color/type/spacing decision.
2. **`MIGRATION_PLAN.md`** — audit methodology + safe-first rules for the full Flask migration. Read this BEFORE touching `flask_app/`.
3. **`COMPONENT_MAP.md`** — maps each `ui_kits/booking/*.jsx` component to its Jinja template equivalent, with class-level diffs.
4. **`colors_and_type.css`** — CSS custom properties you can consume directly if a template needs tokens (most don't — Tailwind utilities suffice).

## Supporting reference

- `ui_kits/booking/*.jsx` — visual reference only, NOT production code. These are the pixel-perfect target look. Translate their className strings into Jinja templates; do not port the JSX structure.
- `preview/*.html` — standalone design-system cards showing tokens, components, and states. Useful when you need to see a single component in isolation.
- `assets/` — logo marks (regular, white, mark-only, favicon). Copy these into `flask_app/app/static/` if needed; do not redraw.
- `fonts/README.md` — Sarabun loader note (Google Fonts CDN; local TTFs not shipped).

## Safe-first operating rules

The user's explicit instruction: **"ถ้าเปลี่ยนแล้วมีปัญหากับการทำงานของโปรแกรม ไม่ควรทำ"** (if a change risks breaking the program, don't do it).

Apply these constraints on every edit:

- **Visuals only.** Change Tailwind classes, HTML structure inside a Jinja block, and inline `<style>`. Do not change:
  - Route handlers (`flask_app/app/routes/`)
  - Database models, migrations, forms
  - Jinja block/inheritance structure (`{% block %}`, `{% extends %}`) unless it's obviously safe
  - `url_for()`, `csrf_token()`, form field names, form action URLs
  - `{{ form.field() }}` rendered output — Flask-WTF generates the `<input>`; you style the wrapper/label around it
- **Preserve every Jinja variable, filter, and control flow.** `{{ user.name }}`, `{% for %}`, `{% if %}` keep their semantics.
- **Preserve CSRF and form integrity.** If you can't tell what a block does, leave it alone.
- **Test each page still renders** after a change. If you can run `flask run`, do it and eyeball the page. Do not merge visually-changed templates without seeing them render.
- **Small diffs > big diffs.** One page per commit. Easy to revert.
- **Flag thematic decisions.** If a content string in Thai needs rewriting to match the skill's tone guide, do NOT rewrite silently — call it out in the PR/commit message so the product owner can approve. Treat product copy as a separate approval surface from visual changes.
- **i18n is user-deferred.** The user hasn't decided whether to use Flask-Babel. Default behavior: keep Thai strings as Jinja-embedded literals exactly as they are today. Do not introduce gettext wrappers unless asked.

## Full-migration workflow (the user picked "Full migration")

1. **Audit first.** Walk every template under `flask_app/app/templates/`. For each, produce a short diff report: what classes/structure differ from the target (ui_kits/booking + README). Commit the audit as `MIGRATION_AUDIT.md` at the repo root before touching any template.
2. **Prioritize impact.** Public booking flow first (every patient sees it), then landing, then auth, then tenant dashboard, then settings screens, then success/email.
3. **One page at a time.** Edit template → restart dev server → eyeball → commit. Never batch multiple pages in one commit.
4. **Macro refactors are opt-in.** If the same button/card markup appears 3+ times, THEN lift a Jinja macro into `flask_app/app/templates/macros/_buttons.html`, etc. Don't pre-factor.
5. **Admin panel:** skip. Unless the user explicitly asks.

## Iconography substitution rule

The original codebase has inline Heroicons hand-copied as `<svg>`. Keep that pattern — do NOT introduce a new icon library or icon font. If a template is missing an icon, copy the SVG markup from `ui_kits/booking/icons.jsx` (the same path data, same stroke-width).

**Logout icon:** the codebase historically uses 🚪 emoji. The design system has since replaced this with the `arrow-right-on-rectangle` Heroicon (outline, stroke-2). When you touch a template that uses the emoji, swap it to the SVG. Everywhere else, the sanctioned emoji set stays (see README Iconography).

## Dates + currency + phones

- Dates: Thai Buddhist calendar (year + 543). If a template renders `{{ booking.date.strftime('%Y') }}`, that's CE — wrap with a Jinja filter. Check if `flask_app/app/` already has a `thai_date` filter before adding one.
- Currency: `฿1,990/เดือน` — Thai baht sign, comma thousands.
- Phone: `08x-xxx-xxxx` (mobile) / `02-xxx-xxxx` (landline).

## When the user invokes this skill with a vague ask

Ask these before proceeding:

1. "หน้าไหน?" (which page / template path)
2. "visual อย่างเดียวใช่ไหม หรือว่าปรับ structure ด้วย?"
3. "มี component mapping ใน COMPONENT_MAP.md อยู่แล้วให้ใช้อ้างอิงไหม?"

If they say "ทำทั้งหมด" — start from the audit step, not from random editing.
