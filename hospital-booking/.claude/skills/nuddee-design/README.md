# NudDee Design System

> **นัดดี** — *nát-dii*, roughly "a good appointment"
> Multi-tenant online appointment-booking SaaS for Thai hospitals, clinics, and specialty centres.

---

## What is NudDee?

NudDee is a Thai-first SaaS platform that lets healthcare providers (hospitals, clinics, dental, specialty centres) offer online appointment booking to their patients. Each tenant gets its own subdomain (`humnoi.nuddee.com`) and its own admin dashboard; patients book through a public booking page without logging in.

The platform is structured as three distinct surfaces, each with its own voice and visual language:

| Surface | Users | Stack | Purpose |
|---|---|---|---|
| **Marketing + Tenant App** (`flask_app/`) | Hospital admins, patients | Flask + Jinja + Tailwind CDN + Sarabun | Landing, pricing, signup; tenant dashboards; public booking flow |
| **API** (`fastapi_app/`) | Internal only | FastAPI | Availability, bookings, Stripe webhooks — no UI |
| **Super Admin** (`admin_app/`) | NudDee staff | Flask + Bootstrap 5 + FontAwesome | Tenant management, audit logs — *visually distinct from brand* |

The **Marketing + Tenant App** is the canonical brand surface. This design system codifies its visual language. The Super Admin panel uses Bootstrap defaults and is out of scope for the public brand.

---

## Sources

Everything here is extracted from:

- **Codebase:** `kaebmoo/nandt` on GitHub, subtree `hospital-booking/` (branch `main`)
  - `flask_app/app/templates/` — all public Jinja templates (landing, booking flow, dashboard, auth)
  - `flask_app/app/templates/base.html` + `partials/navbar.html` — global chrome
  - `admin_app/static/css/admin.css` — admin panel (reference only)
- **No Figma** was provided. All visual values are lifted directly from Tailwind class usage in the templates.
- **No icon library file** ships with the repo — the app uses inline Heroicons via `<svg>` + emoji. We've cataloged the set we see in the templates.

---

## Index

| File | What's in it |
|---|---|
| `README.md` | This file — product context, content rules, visual foundations, iconography |
| `SKILL.md` | Agent-Skill wrapper so this design system can be used as a Claude Code skill |
| `colors_and_type.css` | CSS custom properties for colors + type; drop-in stylesheet |
| `fonts/` | Sarabun webfont loader (via Google Fonts — see note) |
| `assets/` | Logo marks, favicons, illustrations, reference screenshots |
| `preview/` | Design-system cards (typography, color, spacing, components) rendered for the Design System tab |
| `ui_kits/booking/` | React recreation of the public booking flow + marketing landing (patient-facing) |

---

## Content Fundamentals

NudDee's copy is **Thai-first, polite-formal, and slightly warm**. English appears only in product names (NudDee, Basic, Professional, Enterprise, Dashboard) and technical labels (Custom Domain, API Access, SLA).

### Language & register

- **Thai throughout** — UI, email, error messages. English is a fallback, never the default.
- **Polite formal register** using `กรุณา` ("please"), `ขอบคุณ` ("thank you"), and the full polite particle `ครับ/ค่ะ` in conversational copy. Never casual slang.
- **No personal pronouns when avoidable.** The product doesn't say "we/our" (`เรา`); it speaks in the third-person passive ("ระบบจะ…", "the system will…"). When addressing the user it uses `คุณ` ("you", polite).
- **Imperative verbs for actions** — `เลือก`, `ยืนยัน`, `เริ่มต้น`, `ดำเนินการต่อ` ("choose", "confirm", "start", "continue").
- **Thai Buddhist calendar** for dates: year is converted to `B.E.` by adding 543. E.g. 2025 CE → 2568 BE. Dates render `${thai_day_name} ${day} ${thai_short_month} ${BE_year}`.

### Concrete examples

| Context | Thai copy | Literal |
|---|---|---|
| Hero headline | `ระบบนัดหมายออนไลน์สำหรับผู้ให้บริการ` | Online appointment system for providers |
| Hero subhead | `จัดการนัดหมาย ลดเวลารอ เพิ่มประสิทธิภาพ` | Manage appointments, reduce wait, improve efficiency |
| Primary CTA (guest) | `ทดลองใช้ฟรี 14 วัน` | Try free for 14 days |
| Secondary CTA | `ขอสาธิตการใช้งาน` | Request a demo |
| Booking step label | `เลือกวันเวลา` → `กรอกข้อมูล` → `ยืนยันการจอง` | Pick date/time → Fill info → Confirm booking |
| Success heading | `จองนัดหมายสำเร็จ!` | Appointment booked successfully! |
| Reminder | `กรุณามาถึงก่อนเวลานัด 15 นาที` | Please arrive 15 minutes before your appointment |
| Empty state | `ยังไม่มีประเภทการนัดหมาย` | No appointment types yet |
| Validation | `กรุณากรอกอีเมลหรือเบอร์โทรอย่างน้อย 1 อย่าง` | Please enter at least email or phone |

### Microcopy patterns

- **Required marker:** red asterisk `*` with label `ชื่อ-นามสกุล <span class="text-red-500">*</span>`.
- **Optional marker:** gray parenthetical after the label: `เบอร์โทร (ไม่บังคับ)` or `(ถ้ามี)`.
- **Helper text:** gray, 12px, directly under the field: `ใช้สำหรับส่งการยืนยันและติดต่อกลับ`.
- **Emoji in dropdowns and menus:** 🏥 Dashboard, 👤 โปรไฟล์, 🕐 ตั้งค่าเวลาทำการ, 📅 ประเภทการนัดหมาย, 🚪 ออกจากระบบ. **Do not add new emoji** — stick to the existing set.
- **Celebration emoji** appears in flash messages and alerts only: `🎉 สร้างบัญชีทดลองใช้สำเร็จ!`, `📞 ทีมงานจะติดต่อกลับภายใน 24 ชั่วโมง`.
- **Phone format:** Thai mobile `08x-xxx-xxxx`, landline `02-xxx-xxxx`.
- **Currency:** `฿1,990/เดือน` — Thai baht sign, thousands comma, `/เดือน` for monthly.

### Tone

Friendly-professional, never jokey. The booking flow is reassuring: "หลังจากยืนยันการจอง คุณจะได้รับอีเมลยืนยันพร้อมรายละเอียดการนัดหมาย" ("After you confirm, you'll receive a confirmation email with appointment details"). Errors are blunt and actionable: "รูปแบบอีเมลไม่ถูกต้อง" ("Email format is invalid"), not apologetic.

---

## Visual Foundations

### Colors

The palette is **Tailwind's default palette**, consumed via `bg-purple-*`, `text-purple-*`, etc. No custom color tokens are defined in the repo. The system uses four distinct color roles:

- **Primary — Purple.** `purple-600 #9333ea` for all primary actions; `purple-700 #7e22ce` on hover; `purple-100 #f3e8ff` for filled avatar/icon badges; `purple-50 #faf5ff` for panel backgrounds.
- **Accent — Blue.** `blue-600 #2563eb` pairs with purple in the signature gradient `from-purple-600 to-blue-600`. Also used standalone for informational icons and `blue-50` info cards.
- **Hero gradient — Indigo/Violet.** Hand-picked CSS `linear-gradient(135deg, #667eea 0%, #764ba2 100%)`. This is the *one* custom color pair in the system, used exclusively on the landing-page hero.
- **Neutrals — Gray.** `gray-50` page bg, `gray-100` disabled/empty states, `gray-200` borders, `gray-300` placeholder button states, `gray-400` icon-faded, `gray-500` helper text, `gray-600` body, `gray-700` label, `gray-800` foreground, `gray-900` headings, footer bg.
- **Semantic.** Green `green-500/600` for checkmarks and success; Red `red-500` required/errors; Yellow `yellow-500` warnings; Blue `blue-500` info.

### Type

- **Family:** `'Sarabun', sans-serif` — loaded from Google Fonts, weights 300 / 400 / 600 / 700. No other families; no serif; no monospace except a `font-mono` utility used once for booking-reference codes.
- **Display scale:** `text-5xl` (48px) hero h1, `text-3xl` (30px) section h2 / page h1, `text-2xl` (24px) modal/auth h2, `text-xl` (20px) card titles / nav brand, `text-lg` (18px) subheadings, `text-base` (16px) body, `text-sm` (14px) labels / nav items, `text-xs` (12px) helper text.
- **Weight:** `font-bold` (700) for headings and wordmark; `font-semibold` (600) for labels and strong UI text; `font-medium` (500) for buttons and emphasis; `font-normal` (400) for body. 300 is loaded but essentially unused.
- **Leading:** default Tailwind (`leading-normal` ≈ 1.5). No custom line-height tokens.

### Spacing & layout

- **Container:** `container mx-auto px-4` or `max-w-6xl mx-auto px-4` (marketing) / `max-w-4xl` (forms) / `max-w-2xl` (success) / `max-w-md` (auth).
- **Section padding:** `py-16` or `py-20` on marketing sections; `py-8` on app content areas; `py-6` on panel headers.
- **Card padding:** `p-6` standard, `p-8` on larger cards, `p-12` on empty states.
- **Gap:** `space-y-3`/`space-y-4` inside forms, `gap-6`/`gap-8` on grids.
- **Grid:** marketing uses `grid md:grid-cols-3 gap-8` for features, `md:grid-cols-4 gap-8 max-w-6xl` for pricing; booking uses `grid grid-cols-1 lg:grid-cols-5 gap-8` (3/2 split).

### Backgrounds

- **Page:** flat `bg-gray-50`.
- **Booking flow:** soft diagonal wash `bg-gradient-to-br from-purple-50 to-blue-50`.
- **Success page:** `bg-gradient-to-br from-green-50 to-blue-50`.
- **Hero:** custom indigo gradient at 135°.
- **Cards:** always solid `bg-white`.
- **No imagery, no illustrations, no patterns, no textures.** The system is clean and typographic — no hand-drawn elements.

### Cards, borders, radius, shadow

- **Card:** `bg-white rounded-xl shadow-md p-6` is the canonical card.
- **Hover:** `hover:shadow-xl` plus `transform: translateY(-2px)` or `-10px` on pricing plans; 0.2s–0.3s ease transition.
- **Popular plan:** 2px `border-purple-600` + ribbon tag absolutely positioned at `-top-4 left-1/2`.
- **Radius scale:** `rounded-lg` (8px) for buttons, inputs, small chips; `rounded-xl` (12px) for cards; `rounded-full` for avatars and badges.
- **Borders:** `border border-gray-300` on inputs; `border-b` (1px) between dashboard sections; `border-2` only on the emphasized Popular card.
- **Shadows:** `shadow-sm` on nav (sticky top), `shadow-md` on cards, `shadow-lg` on modal/pricing defaults, `shadow-xl` on pricing-card hover and modal contents. No custom shadow tokens — all Tailwind presets.

### Buttons

- **Primary solid:** `bg-purple-600 text-white px-6 py-2 rounded-lg hover:bg-purple-700 transition-colors`.
- **Primary gradient:** `bg-gradient-to-r from-purple-600 to-blue-600 text-white ... hover:from-purple-700 hover:to-blue-700` — used on high-emphasis conversion CTAs (hero, booking confirm, add-to-calendar).
- **Secondary outline:** `border-2 border-white` on gradient bg (reverses on hover); `border border-gray-300 text-gray-700 hover:bg-gray-50` on light bg.
- **Ghost link:** `text-purple-600 hover:text-purple-700` with optional `hover:underline`.
- **Disabled:** `bg-gray-300 text-white cursor-not-allowed`.
- **Sizes:** standard `py-2 px-4` or `py-2 px-6`; large CTA `py-3 px-8`; full-width `w-full py-2` on modals.

### Forms

- Input: `w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent`.
- Checkbox: `h-4 w-4 text-purple-600 border-gray-300 rounded focus:ring-purple-500`.
- Select: same as input + chevron.
- Label: `block text-sm font-medium text-gray-700 mb-1`.
- Helper: `text-xs text-gray-500 mt-1`.

### Animation & interactions

- **Transitions:** `transition-colors`, `transition-all`, `transition-shadow`, all `duration-200` to `duration-300` with `ease` or `ease-in-out`. No bounces, no springs, no elastic curves.
- **Hover lift:** pricing cards `translateY(-10px)`, event cards `translateY(-2px)`.
- **Focus ring:** `ring-2 ring-purple-500` with `ring-offset-2` on primary buttons.
- **Press state:** none explicit — relies on browser default `:active`.
- **Loading spinner:** `animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600`.
- **Custom keyframe:** `@keyframes checkmark` on the booking-success tick (draws the check).
- **Modal entrance:** opacity toggle via `hidden` class — no custom keyframes.
- **Flash message:** custom `@keyframes slideInTop` — fade + 20px downward slide, 0.3s.

### Calendar (booking)

Distinctive component with color-coded day states:
- `.available` — `bg-gray-100`, `bg-indigo-100` on hover
- `.selected` — `bg-indigo-600 text-white`
- `.holiday` / `.special-closure` — `bg-red-100 text-rose-700` with "ปิด" label
- `.blocked` (beyond range) — `bg-red-50 text-red-800`
- `.today` — 2px `border-indigo-600`
- `.past` / `.disabled` — `text-gray-300/400`, `cursor-not-allowed`

Weekday header uses Thai short names อา จ อ พ พฤ ศ ส, with Sunday in red.

### Progress stepper

Horizontal step indicator on booking flow: `w-8 h-8 rounded-full` circles numbered 1–3, connected by a 1px bar. Active step: `bg-purple-600 text-white` + `text-purple-600` label. Completed: `bg-green-600` with a check icon. Future: `bg-gray-300` + `text-gray-400`. Connector line fills purple as you progress.

### Fixed elements

- **Sticky nav:** `sticky top-0 z-50` with `bg-white shadow-sm border-b`, height 64px.
- **Sticky summary:** booking confirm page uses `sticky top-4` on the right-column summary card.
- **Modal:** `fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center`.
- **Dropdown:** absolutely positioned `mt-2 w-48 bg-white rounded-md shadow-lg py-1 z-50` with `opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200`.

### Transparency & blur

Essentially unused. The only transparency is the modal backdrop (`bg-black bg-opacity-50`) and dropdown enter/exit. **No backdrop-blur anywhere.** Keep it that way — it's not in the vocabulary.

---

## Iconography

### What the repo actually uses

**Inline Heroicons, hand-copied as `<svg>` in templates.** There's no icon font, no SVG sprite, no icon component. Every icon is a literal `<svg class="w-N h-N text-X">...<path .../>` inside the HTML. Stroke weight is `stroke-width="2"` (Heroicons Outline default) or `fill="currentColor"` with `viewBox="0 0 20 20"` (Heroicons Solid default).

**The icon set in use** (what we found across templates):

| Purpose | Heroicon name | Where used |
|---|---|---|
| Logo lightning bolt | `bolt` (solid, 20×20) | NudDee wordmark |
| Calendar | `calendar` (outline, 24×24) | Features, dashboard menu, pricing |
| Phone / mobile | `device-mobile` (outline) | Features |
| Chart bar | `chart-bar` (outline) | Reports feature |
| Clock | `clock` (outline) | Event-type duration, advance-notice helper |
| Info circle | `information-circle` (outline) | Form helper, notes |
| Check (solid) | `check` (solid, 20×20) | Pricing checkmarks, success tick |
| X / close | `x` (outline) | Modal close, alert dismiss |
| Chevron left/right/down | `chevron-*` (outline) | Calendar nav, back button, dropdown caret |
| Search | `search` (outline) | "Find my booking" CTA |
| Logout | `arrow-right-on-rectangle` (outline) | Profile menu — replaces the earlier 🚪 emoji for a more professional feel |
| Exclamation / warning | `exclamation-circle` (outline) | Error states |

**Copy these from the official Heroicons library** (MIT-licensed, [heroicons.com](https://heroicons.com)) — do not redraw them. We link the library via CDN in the UI kit rather than bundling.

### Emoji

Emoji are a first-class icon type in NudDee, used in **menu items and flash messages only**:

| Menu item | Emoji |
|---|---|
| Dashboard | 🏥 |
| โปรไฟล์ (Profile) | 👤 |
| ตั้งค่าเวลาทำการ (Availability) | 🕐 |
| ประเภทการนัดหมาย (Event types) | 📅 |
| จัดการวันหยุด (Holidays) | 📅 |
| จัดการผู้ให้บริการ (Providers) | 👥 |
| หน้าจองสาธารณะ (Public booking) | 🔗 |
| หน้าหลัก (Home) | 🏠 |

And in interstitial feedback: 🎉 (success), 📞 (call), 🔍 (demo hint).

**Rule:** don't introduce new emoji. Keep the set small and consistent — the Heroicons do the heavy lifting everywhere else.

### Logos

The "logo" is a purple lightning-bolt Heroicon (`text-purple-600`) next to the wordmark **NudDee** (bold, gray-900 on light, white on dark). Sizes:
- Nav: `w-8 h-8` bolt + `text-xl font-bold` wordmark
- Auth page: `w-10 h-10` bolt + `text-2xl font-bold` wordmark
- Footer: `w-8 h-8` bolt (`text-purple-400`) + `text-xl font-bold` white wordmark

There is **no separate logotype file** in the repo. We've recreated a standalone SVG in `assets/logo-nuddee.svg` for use outside HTML contexts.

### Substitutions flagged for the user

- **Sarabun** is loaded via Google Fonts CDN in every template — we reference it the same way. If you want a local fallback, grab the TTFs from [Google Fonts: Sarabun](https://fonts.google.com/specimen/Sarabun) and drop them in `fonts/`. **Currently the system uses the CDN only — no local font files shipped.**
- **Logo mark** — the purple lightning-bolt is the in-repo brand mark. If NudDee has a dedicated logotype (stacked or horizontal lockup), it wasn't in the repo; flag to designer to provide.
- **Admin panel aesthetic** (Bootstrap 5 + FontAwesome) is intentionally omitted from this system; it's an internal tool with a different visual language. If you need it, reference `admin_app/static/css/admin.css` directly.
