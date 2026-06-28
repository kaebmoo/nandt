# Subdomain URL Generation - Analysis and Fixes

## ปัญหาที่พบ

จากการวิเคราะห์ code พบว่ามีปัญหาการจัดการ subdomain ที่ไม่สม่ำเสมอ ทำให้เกิด URL แบบ `http://humnoi.localhost/dashboard?subdomain=humnoi` แทนที่จะเป็นแค่ `http://humnoi.localhost/dashboard`

## Root Cause Analysis

### 1. การใช้ `url_for` โดยตรงแทนการใช้ Helper Functions
**ตำแหน่งปัญหา:**
- `routes.py:267, 386, 413, 429, 488, 499, 506` - ใช้ `url_for('main.dashboard', subdomain=subdomain)` โดยตรง
- Template files - ใช้ `url_for` โดยตรงในหลายจุด

**ผลกระทบ:**
- เมื่อใช้ `url_for` พร้อม `subdomain` parameter จะเพิ่ม `?subdomain=xxx` เข้าไปใน URL เสมอ
- แม้ว่าจะเข้าผ่าน subdomain hostname แล้วก็ตาม

### 2. การไม่ใช้ Helper Functions ที่มีอยู่แล้ว
**Helper Functions ที่มีอยู่:**
- `nav_url()` - Template function ที่ wrapper `NavigationHelper.url_for_with_subdomain()`
- `smart_url_for()` - Template function ที่ wrapper `build_url_with_context()`
- `build_url_with_context()` - Utility function ใน `url_helper.py`

**ปัญหา:**
- Functions เหล่านี้ไม่ได้ถูกใช้อย่างสม่ำเสมอ
- บางจุดใช้ `url_for` โดยตรงแทน

## แนวทางแก้ไข

### 1. แก้ไขในไฟล์ Python Routes

#### 1.1 routes.py
```python
# ❌ เก่า - ใช้ url_for โดยตรง
return redirect(url_for('main.dashboard', subdomain=subdomain))

# ✅ ใหม่ - ใช้ helper function
from .utils.url_helper import build_url_with_context
return redirect(build_url_with_context('main.dashboard'))
```

**จุดที่ต้องแก้:**
- Line 267: `return redirect(url_for('main.dashboard', subdomain=subdomain))`
- Line 386: `return redirect(url_for('main.dashboard', subdomain=subdomain))`
- Line 413: `return redirect(url_for('main.dashboard', subdomain=subdomain))`
- Line 429: `return redirect(url_for('main.dashboard', subdomain=subdomain))`
- Line 488: `return redirect(url_for('main.dashboard', subdomain=subdomain))`
- Line 499: `return redirect(url_for('main.dashboard', subdomain=subdomain))`
- Line 506: `return redirect(url_for('main.dashboard', subdomain=subdomain))`

#### 1.2 public_booking.py
```python
# ❌ เก่า
return redirect(url_for('booking.booking_home', subdomain=subdomain))

# ✅ ใหม่
from .utils.url_helper import build_url_with_context
return redirect(build_url_with_context('booking.booking_home'))
```

**จุดที่ต้องแก้:**
- Line 316: `return redirect(url_for('booking.booking_home', subdomain=subdomain))`
- Line 323: `return redirect(url_for('booking.booking_home', subdomain=subdomain))`

#### 1.3 with_tenant Decorator Enhancement
ปรับปรุง `core/tenant_manager.py` ใน decorator `with_tenant()`:

```python
# เพิ่มในบรรทัดหลัง line 160
g.tenant_schema = f"tenant_{subdomain}" if subdomain else None
g.subdomain = subdomain

# เพิ่มการตรวจสอบว่า subdomain มาจาก hostname หรือ parameter
hostname = request.host.split(':')[0]
if '.' in hostname and hostname.split('.')[0] == subdomain:
    g.subdomain_from_host = True
else:
    g.subdomain_from_host = False
```

### 2. แก้ไขในไฟล์ Templates

#### 2.1 ใช้ `nav_url` แทน `url_for` ในทุกที่
**Template files ที่ต้องแก้:**

##### dashboard.html
```html
<!-- ❌ เก่า -->
<a href="{{ url_for('booking.booking_home', subdomain=subdomain) }}">

<!-- ✅ ใหม่ -->
<a href="{{ nav_url('booking.booking_home') }}">
```

**จุดที่ต้องแก้:**
- Line 119: `url_for('booking.booking_home', subdomain=subdomain)`
- Line 201: `url_for('main.view_appointment', appointment_id=appointment.id, subdomain=subdomain)`
- Line 208: `url_for('main.admin_reschedule_appointment', appointment_id=appointment.id, subdomain=subdomain)`
- Line 214: `url_for('main.admin_cancel_appointment', appointment_id=appointment.id, subdomain=subdomain)`
- Line 283: `url_for('main.view_appointment', appointment_id=appointment.id, subdomain=subdomain)`
- Line 359: `url_for('main.view_appointment', appointment_id=appointment.id, subdomain=subdomain)`
- Line 366: `url_for('main.restore_appointment', appointment_id=appointment.id, subdomain=subdomain)`
- Line 376: `url_for('main.delete_appointment', appointment_id=appointment.id, subdomain=subdomain)`

##### appointments/view.html
```html
<!-- ❌ เก่า -->
<a href="{{ url_for('main.dashboard', subdomain=subdomain) }}">

<!-- ✅ ใหม่ -->
<a href="{{ nav_url('main.dashboard') }}">
```

**จุดที่ต้องแก้:**
- Line 20: `url_for('main.dashboard', subdomain=subdomain)`
- Line 125: `url_for('main.admin_reschedule_appointment', appointment_id=appointment.id, subdomain=subdomain)`
- Line 132: `url_for('main.admin_cancel_appointment', appointment_id=appointment.id, subdomain=subdomain)`
- Line 138: `url_for('main.dashboard', subdomain=subdomain)`

##### appointments/admin_cancel.html
```html
<!-- ❌ เก่า -->
<a href="{{ url_for('main.dashboard', subdomain=subdomain) }}">

<!-- ✅ ใหม่ -->
<a href="{{ nav_url('main.dashboard') }}">
```

**จุดที่ต้องแก้:**
- Line 41: `url_for('main.dashboard', subdomain=subdomain)`

##### appointments/admin_reschedule.html
```html
<!-- ❌ เก่า -->
<a href="{{ url_for('main.dashboard', subdomain=subdomain) }}">

<!-- ✅ ใหม่ -->
<a href="{{ nav_url('main.dashboard') }}">
```

**จุดที่ต้องแก้:**
- Line 59: `url_for('main.dashboard', subdomain=subdomain)`

##### booking/manage.html
```html
<!-- ❌ เก่า -->
<a href="{{ url_for('booking.reschedule_booking', reference=booking.booking_reference, subdomain=subdomain) }}">

<!-- ✅ ใหม่ -->
<a href="{{ nav_url('booking.reschedule_booking', reference=booking.booking_reference) }}">
```

**จุดที่ต้องแก้:**
- Line 46: `url_for('booking.reschedule_booking', reference=booking.booking_reference, subdomain=subdomain)`
- Line 53: `url_for('booking.cancel_booking', reference=booking.booking_reference, subdomain=subdomain)`
- Line 63: `url_for('booking.booking_home', subdomain=subdomain)`

##### booking/reschedule.html
```html
<!-- ❌ เก่า -->
<a href="{{ url_for('booking.manage_booking', reference=booking.booking_reference, subdomain=subdomain) }}">

<!-- ✅ ใหม่ -->
<a href="{{ nav_url('booking.manage_booking', reference=booking.booking_reference) }}">
```

**จุดที่ต้องแก้:**
- Line 55: `url_for('booking.manage_booking', reference=booking.booking_reference, subdomain=subdomain)`
- Line 87: `url_for('booking.reschedule_booking', reference=booking.booking_reference, subdomain=subdomain)`
- Line 183: `url_for('booking.manage_booking', reference=booking.booking_reference, subdomain=subdomain)`

##### partials/navbar.html
```html
<!-- ❌ เก่า -->
<a href="{{ url_for('booking.booking_home', subdomain=nav_params.subdomain) }}">

<!-- ✅ ใหม่ -->
<a href="{{ nav_url('booking.booking_home') }}">
```

**จุดที่ต้องแก้:**
- Line 58: `url_for('booking.booking_home', subdomain=nav_params.subdomain)`

### 3. ปรับปรุง Helper Functions

#### 3.1 เพิ่ม Logic ใน NavigationHelper
```python
# ในไฟล์ app/helpers/navigation.py
@staticmethod
def url_for_with_subdomain(endpoint, **kwargs):
    """
    สร้าง URL ที่จัดการเรื่อง subdomain ให้อัตโนมัติ
    - ถ้า subdomain มาจาก hostname (เช่น humnoi.localhost), จะไม่เติม query parameter
    - ถ้า subdomain มาจาก query parameter, จะเติม ?subdomain=... เข้าไปใน URL
    """
    is_from_host = getattr(g, 'subdomain_from_host', False)
    
    # ถ้าไม่ได้มาจาก Hostname และมี subdomain อยู่ใน g
    # ให้เพิ่ม subdomain เข้าไปใน parameters ของ URL
    if not is_from_host and hasattr(g, 'subdomain') and g.subdomain:
        kwargs.setdefault('subdomain', g.subdomain)
    
    # สร้าง URL ตามปกติด้วย url_for
    return url_for(endpoint, **kwargs)
```

#### 3.2 ปรับปรุง build_url_with_context
```python
# ในไฟل์ app/utils/url_helper.py
def build_url_with_context(endpoint, **kwargs):
    """Build URL with appropriate tenant context"""
    from flask import url_for, g
    
    # Get current subdomain
    subdomain = kwargs.pop('subdomain', None)
    if not subdomain:
        subdomain = getattr(g, 'subdomain', None)
    
    # Check if subdomain comes from hostname
    is_from_host = getattr(g, 'subdomain_from_host', False)
    
    # Only add subdomain param if needed (not from hostname)
    if subdomain and not is_from_host and needs_subdomain_param():
        kwargs['subdomain'] = subdomain
    
    return url_for(endpoint, **kwargs)
```

## การแก้ไขสำคัญในลำดับความสำคัญ

### Priority 1: Core Route Redirects
1. แก้ไข `routes.py` ทุกจุดที่ใช้ `url_for('main.dashboard', subdomain=subdomain)`
2. แก้ไข `public_booking.py` ทุกจุดที่ใช้ `url_for` พร้อม subdomain parameter

### Priority 2: Template Updates  
1. แก้ไข `dashboard.html` - มีการใช้ `url_for` มากที่สุด
2. แก้ไข `partials/navbar.html` - ส่งผลต่อทุกหน้า
3. แก้ไข template files อื่นๆ ตามลำดับ

### Priority 3: Helper Function Enhancement
1. ปรับปรุง `with_tenant` decorator ให้ set `g.subdomain_from_host` อย่างถูกต้อง
2. ปรับปรุง helper functions ให้ทำงานได้ดีขึ้น

## Expected Result

หลังจากการแก้ไข:
- `http://humnoi.localhost/dashboard` → ไม่มี query parameter
- `http://localhost/dashboard?subdomain=humnoi` → มี query parameter 
- URL generation จะ smart ตามสภาพแวดล้อมที่เหมาะสม

## การทดสอบ

### Test Cases ที่ควรทดสอบ:
1. เข้าผ่าน subdomain: `http://humnoi.localhost/dashboard`
   - ตรวจสอบว่า navigation links ไม่มี `?subdomain=humnoi`
2. เข้าผ่าน query param: `http://localhost/dashboard?subdomain=humnoi`
   - ตรวจสอบว่า navigation links มี `?subdomain=humnoi`
3. การ redirect จาก form submissions
4. การ navigate ระหว่างหน้าต่างๆ

## Implementation Steps

1. **Phase 1**: แก้ไข Python routes (Priority 1)
2. **Phase 2**: แก้ไข templates หลัก (Priority 2)  
3. **Phase 3**: ปรับปรุง helper functions (Priority 3)
4. **Phase 4**: Testing และ refinement

การแก้ไขนี้จะทำให้ URL generation สะอาดขึ้นและมีความสอดคล้องกันมากขึ้น ตรงตามความต้องการที่จะรองรับทั้งแบบ subdomain และแบบ query parameter โดยไม่ให้เกิดความซ้ำซ้อน