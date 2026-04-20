# Component Map — JSX reference → Jinja template

This maps each JSX component in `ui_kits/booking/` to the class vocabulary you'd apply in the Flask templates.

The JSX files are **visual reference**, not code to port. Copy the `className` strings, the HTML structure, and the exact hex values — not the React logic.

---

## Primitives — `ui.jsx`

### Button

```html
<!-- Primary solid -->
<button class="inline-flex items-center justify-center px-4 py-2 text-sm font-medium rounded-lg bg-purple-600 text-white hover:bg-purple-700 transition-colors">...</button>

<!-- Primary gradient (high-emphasis conversion) -->
<button class="inline-flex items-center justify-center px-4 py-2 text-sm font-medium rounded-lg text-white bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700 transition-colors">...</button>

<!-- Secondary outline -->
<button class="inline-flex items-center justify-center px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 bg-white hover:bg-gray-50 transition-colors">...</button>

<!-- Ghost link -->
<a class="text-purple-600 hover:text-purple-700 hover:underline text-sm font-medium">...</a>

<!-- Disabled -->
<button class="inline-flex items-center justify-center px-4 py-2 text-sm font-medium rounded-lg bg-gray-300 text-white cursor-not-allowed" disabled>...</button>
```

Sizes: `sm` = `px-3 py-1.5 text-sm`, `md` (default) = `px-4 py-2 text-sm`, `lg` = `px-6 py-2 text-base`, `xl` = `px-8 py-3 text-lg`.

### Card

```html
<div class="bg-white rounded-xl shadow-md p-6">...</div>
```

Hover-lift variant (pricing, event cards): add `transition-all hover:shadow-xl` + inline `style="transform: translateY(-2px)"` on `:hover` (use a utility or custom style).

### Field (label + input + helper)

```html
<div>
  <label for="name" class="block text-sm font-medium text-gray-700 mb-1">
    ชื่อ-นามสกุล <span class="text-red-500">*</span>
  </label>
  <input id="name" name="name" type="text" required
         class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent">
  <p class="text-xs text-gray-500 mt-1">ใช้สำหรับส่งการยืนยันและติดต่อกลับ</p>
</div>
```

Optional marker: `<span class="text-gray-400 font-normal"> (ถ้ามี)</span>`.

Select: same input classes + `bg-white`.

Textarea: same input classes + set `rows`.

Checkbox:
```html
<input type="checkbox" class="h-4 w-4 text-purple-600 border-gray-300 rounded focus:ring-purple-500" style="accent-color: #9333ea">
```

### Flash / Alert

```html
<!-- Success -->
<div class="bg-green-100 text-green-800 border border-green-300 rounded-lg px-4 py-3 text-sm">...</div>
<!-- Error -->
<div class="bg-red-100 text-red-800 border border-red-300 rounded-lg px-4 py-3 text-sm">...</div>
<!-- Info -->
<div class="bg-blue-100 text-blue-800 border border-blue-300 rounded-lg px-4 py-3 text-sm">...</div>
<!-- Warning -->
<div class="bg-yellow-100 text-yellow-800 border border-yellow-300 rounded-lg px-4 py-3 text-sm">...</div>
```

---

## Chrome — `Chrome.jsx`

### Navbar (authenticated tenant)

```html
<nav class="bg-white shadow-sm border-b sticky top-0 z-40">
  <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="flex justify-between items-center h-16">
      <a href="{{ url_for('dashboard.index') }}" class="flex items-center gap-2">
        <!-- Heroicon bolt solid, w-8 h-8 text-purple-600 -->
        <svg class="w-8 h-8 text-purple-600" fill="currentColor" viewBox="0 0 20 20">
          <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z"/>
        </svg>
        <span class="text-xl font-bold text-gray-900">NudDee</span>
      </a>
      <div class="flex items-center gap-4">
        <span class="text-sm text-gray-500 hidden sm:block">{{ current_tenant.name }}</span>
        <!-- user dropdown goes here -->
      </div>
    </div>
  </div>
</nav>
```

### Navbar (public / landing)

Same shell, but replace the user area with:
```html
<div class="flex items-center gap-4">
  <a href="#pricing" class="text-sm text-gray-600 hover:text-purple-600">ราคา</a>
  <a href="#features" class="text-sm text-gray-600 hover:text-purple-600">คุณสมบัติ</a>
  <a href="{{ url_for('auth.login') }}" class="text-sm text-gray-600 hover:text-purple-600">เข้าสู่ระบบ</a>
  <a href="{{ url_for('auth.signup') }}" class="bg-purple-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-purple-700 transition-colors">ทดลองใช้ฟรี</a>
</div>
```

### Footer

See `Chrome.jsx::Footer` — 4-column grid on `gray-900` bg, Sarabun white text, purple-400 logo.

---

## Landing — `Landing.jsx`

### Hero (the one custom gradient)

```html
<section class="text-white py-20" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
  <div class="max-w-6xl mx-auto px-4 grid md:grid-cols-2 gap-12 items-center">
    <div>
      <h1 class="text-5xl font-bold leading-tight mb-4 text-white">...</h1>
      <p class="text-lg text-white/90 mb-8 max-w-lg">...</p>
      <div class="flex flex-wrap gap-4">
        <a class="bg-white text-purple-600 px-8 py-3 rounded-lg font-medium hover:bg-gray-100 transition-colors">...</a>
        <a class="border-2 border-white text-white px-8 py-3 rounded-lg font-medium hover:bg-white hover:text-purple-600 transition-colors">...</a>
      </div>
    </div>
    <!-- right-side illustration or booking preview -->
  </div>
</section>
```

### Feature card

```html
<div class="text-center">
  <div class="w-12 h-12 bg-purple-100 rounded-xl flex items-center justify-center mx-auto mb-4">
    <!-- Heroicon outline, w-6 h-6 text-purple-600 -->
  </div>
  <h3 class="text-xl font-semibold text-gray-900 mb-2">...</h3>
  <p class="text-gray-600">...</p>
</div>
```

### Pricing card (default)

```html
<div class="bg-white rounded-xl shadow-md p-8 relative">
  <h3 class="text-xl font-bold text-gray-900 mb-1">{{ plan.name }}</h3>
  <p class="text-sm text-gray-500 mb-4">{{ plan.desc }}</p>
  <div class="flex items-baseline gap-1 mb-6">
    <span class="text-sm text-gray-500">฿</span>
    <span class="text-4xl font-bold text-gray-900">{{ plan.price }}</span>
    <span class="text-sm text-gray-500">/เดือน</span>
  </div>
  <ul class="space-y-3 mb-8">
    {% for f in plan.features %}
    <li class="flex gap-2 text-sm text-gray-700 items-start">
      <svg class="w-5 h-5 text-green-500 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
        <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/>
      </svg>
      <span>{{ f }}</span>
    </li>
    {% endfor %}
  </ul>
  <a href="..." class="block w-full py-2 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 text-center font-medium text-sm transition-colors">เลือกแพ็คเกจนี้</a>
</div>
```

### Pricing card (Popular variant)

Swap outer div to:
```html
<div class="bg-white rounded-xl p-8 relative border-2 border-purple-600 shadow-xl">
  <div class="absolute -top-4 left-1/2 -translate-x-1/2 bg-purple-600 text-white text-xs font-semibold px-4 py-1 rounded-full">ยอดนิยม</div>
  ...
```
And the CTA becomes `bg-purple-600 text-white hover:bg-purple-700`.

---

## Booking flow

### Stepper — reusable Jinja macro

Lift into `flask_app/app/templates/macros/_stepper.html`:

```jinja
{% macro stepper(current, labels=['เลือกวันเวลา','กรอกข้อมูล','ยืนยันการจอง']) %}
<div class="flex items-center max-w-2xl mx-auto mb-8">
  {% for label in labels %}
    {% set n = loop.index %}
    {% set done = current > n %}
    {% set active = current == n %}
    <div class="flex items-center">
      <div class="w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold
                  {% if done %}bg-green-600 text-white
                  {% elif active %}bg-purple-600 text-white
                  {% else %}bg-gray-300 text-white{% endif %}">
        {% if done %}
          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>
        {% else %}{{ n }}{% endif %}
      </div>
      <span class="ml-2 text-sm font-medium hidden sm:inline
                  {% if done %}text-green-700{% elif active %}text-purple-600{% else %}text-gray-400{% endif %}">
        {{ label }}
      </span>
    </div>
    {% if not loop.last %}
      <div class="flex-1 h-1 mx-3 rounded-full"
           style="background: {% if done %}#16a34a{% elif active %}#9333ea{% else %}#e5e7eb{% endif %};"></div>
    {% endif %}
  {% endfor %}
</div>
{% endmacro %}
```

Use: `{% from 'macros/_stepper.html' import stepper %}{{ stepper(current=1) }}`.

### Calendar day state classes

```html
<!-- available -->
<div class="rounded-lg text-center py-2.5 text-sm font-medium bg-gray-100 hover:bg-indigo-100 text-gray-900 cursor-pointer">{{ d }}</div>
<!-- selected -->
<div class="... bg-indigo-600 text-white hover:bg-indigo-700">{{ d }}</div>
<!-- today (unselected) -->
<div class="... bg-gray-100 ring-2 ring-indigo-600 ring-inset">{{ d }}</div>
<!-- holiday -->
<div class="... bg-red-100 text-rose-700 cursor-not-allowed">{{ d }}<div class="text-[9px] leading-none mt-0.5">ปิด</div></div>
<!-- past / disabled -->
<div class="... text-gray-300 bg-transparent cursor-not-allowed">{{ d }}</div>
```

### Time slot

```html
<button class="py-2 rounded-lg text-sm font-medium border-2 border-gray-200 hover:border-purple-400 transition-colors bg-white text-gray-900">10:00</button>
<!-- selected -->
<button class="py-2 rounded-lg text-sm font-medium border-2 bg-indigo-600 text-white border-indigo-600">10:00</button>
<!-- disabled -->
<button disabled class="py-2 rounded-lg text-sm font-medium border-2 bg-gray-100 text-gray-400 border-gray-100 line-through cursor-not-allowed">11:30</button>
```

### Sticky summary (booking form right column)

```html
<aside class="lg:col-span-2">
  <div class="sticky top-20 bg-white rounded-xl shadow-md p-6">
    <h3 class="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">สรุปการจอง</h3>
    ...
  </div>
</aside>
```

### Success page check circle

```html
<div class="mx-auto mb-6 flex items-center justify-center w-20 h-20 rounded-full bg-green-100">
  <svg class="w-10 h-10 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/>
  </svg>
</div>
```

Booking reference in mono: `<span class="font-mono text-purple-600 font-semibold">NDD-ABC123</span>`.

---

## Icons — `icons.jsx`

Copy SVG markup directly. Every icon:
- `fill="none" stroke="currentColor"` + `stroke-width="2"` for outline
- `fill="currentColor"` + `viewBox="0 0 20 20"` for solid (bolt, check)

Logout (new — replaces 🚪):
```html
<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
        d="M15.75 9V5.25A2.25 2.25 0 0 0 13.5 3h-6A2.25 2.25 0 0 0 5.25 5.25v13.5A2.25 2.25 0 0 0 7.5 21h6a2.25 2.25 0 0 0 2.25-2.25V15M12 9l3 3m0 0l-3 3m3-3H2.25"/>
</svg>
```

---

## Color quick-reference (Tailwind tokens, use verbatim)

- Primary: `purple-600 #9333ea` · hover `purple-700 #7e22ce` · wash `purple-50 #faf5ff`
- Accent: `blue-600 #2563eb` · gradient `from-purple-600 to-blue-600`
- Hero (landing only): `linear-gradient(135deg, #667eea 0%, #764ba2 100%)`
- Page: `gray-50 #f9fafb`
- Border: `gray-200 #e5e7eb` or `gray-300 #d1d5db` on inputs
- Body: `gray-600 #4b5563` · heading `gray-900 #111827` · muted `gray-500 #6b7280`
- Success: `green-500/600 #22c55e / #16a34a` · Error: `red-500 #ef4444` · Warning: `yellow-500 #eab308` · Info: `blue-500 #3b82f6`

---

## Anything not listed here

If you're about to touch a component or pattern that isn't in this map, STOP. Re-read `README.md` Visual Foundations, check `preview/*.html`, and ask the product owner before inventing.
