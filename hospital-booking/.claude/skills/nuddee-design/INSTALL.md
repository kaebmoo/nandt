# NudDee Design — Claude Code Handoff Package

Drop this whole `nuddee-design/` folder into `hospital-booking/.claude/skills/` in your `nandt` repo clone. Claude Code auto-discovers `SKILL.md` on startup.

## Install (project-local)

```bash
cd /path/to/nandt/hospital-booking
mkdir -p .claude/skills
# copy or unzip this folder so the final layout is:
#   hospital-booking/.claude/skills/nuddee-design/SKILL.md
#   hospital-booking/.claude/skills/nuddee-design/README.md
#   hospital-booking/.claude/skills/nuddee-design/MIGRATION_PLAN.md
#   hospital-booking/.claude/skills/nuddee-design/COMPONENT_MAP.md
#   hospital-booking/.claude/skills/nuddee-design/colors_and_type.css
#   hospital-booking/.claude/skills/nuddee-design/ui_kits/
#   hospital-booking/.claude/skills/nuddee-design/preview/
#   hospital-booking/.claude/skills/nuddee-design/assets/
#   hospital-booking/.claude/skills/nuddee-design/fonts/
```

Commit `.claude/` (or add `.claude/` to `.gitignore` if you want it personal). Project-local skills don't bleed into other repos.

## Invoke

In Claude Code, just start a session inside the repo and say:

> "ใช้ skill `nuddee-design` audit templates ทั้งหมดให้หน่อย"

or

> "ตาม MIGRATION_PLAN.md ทำ Phase 1 (public booking flow) ให้ที"

or

> "เปิด `flask_app/app/templates/public/booking_flow/date_time.html` แล้ว apply visual pass ตาม COMPONENT_MAP.md"

## What's where

| File | Purpose |
|---|---|
| `SKILL.md` | Instructions Claude Code reads first — scope, safe-first rules, workflow |
| `README.md` | Product context, content rules, visual foundations, iconography |
| `MIGRATION_PLAN.md` | 6-phase audit-first migration plan with escalation criteria |
| `COMPONENT_MAP.md` | JSX-reference → Jinja template class/structure mapping |
| `colors_and_type.css` | CSS custom properties (consume directly if needed) |
| `ui_kits/booking/` | React recreation — visual reference, not code to port |
| `preview/` | Standalone HTML cards for each token/component |
| `assets/` | Logo marks (regular, white, mark-only, favicon) |
| `fonts/` | Sarabun loader note (uses Google Fonts CDN) |

## Important guardrails (also repeated in SKILL.md)

1. Do **NOT** modify `fastapi_app/` or `admin_app/` — different scope.
2. Do **NOT** change route handlers, models, forms, or Jinja block inheritance.
3. Visual changes only. Preserve `{{ csrf_token() }}`, form field names, `url_for()`.
4. One page per commit. Test-render each before moving on.
5. Phase 0 = Audit. Commit `MIGRATION_AUDIT.md` BEFORE editing any template.
6. Thai copy changes need product-owner approval — flag, don't silently rewrite.
