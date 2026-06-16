# flask_app/app/queue_routes.py
"""
Routes ของระบบคิว (Phase 1): check-in (patient), staff console, จอแสดงคิว.

Flask-first: business logic อยู่ที่ services/queue_service.py — routes นี้แค่ orchestrate + render Jinja2.
g.db ถูกตั้ง search_path ไป tenant schema แล้วโดย before_request middleware
"""

from flask import Blueprint, render_template, request, flash, redirect, abort, g

from .auth import login_required, get_current_user
from .core.tenant_manager import TenantManager
from .utils.url_helper import build_url_with_context
from .services import grace_service as gs
from .services import identity_service as ids
from .services import priority_service as ps
from .services import queue_notifications as qn
from .services import queue_service as qs
from .services.estimation import get_estimator
from shared_db import models

queue_bp = Blueprint('queue', __name__, url_prefix='/queue')

# ป้ายสถานะภาษาไทย (UI ไทย, code อังกฤษ)
STATUS_TH = {
    'checked_in': 'รอเรียก',
    'called': 'กำลังเรียก',
    'in_service': 'กำลังรับบริการ',
    'done': 'เสร็จแล้ว',
    'no_show': 'ไม่มาตามนัด',
    'skipped': 'ข้ามคิว',
}

# action ปุ่มใน console -> สถานะปลายทาง
_ACTION_TO_STATUS = {
    'start': 'in_service',
    'done': 'done',
    'skip': 'skipped',
    'no-show': 'no_show',
}


def _service_point_or_404(sp_id):
    sp = g.db.query(models.ServicePoint).filter_by(id=sp_id).first()
    if sp is None:
        abort(404)
    return sp


def _deny_if_not_staff():
    """gate สำหรับหน้า/แอ็กชันของเจ้าหน้าที่ — ตรวจ login + สิทธิ์ tenant โดยไม่ปิด g.db

    (ไม่ใช้ auth.check_tenant_access เพราะมันเรียก db.close() ทำให้ search_path ของ g.db หลุด)
    คืน redirect response ถ้าไม่ผ่าน, คืน None ถ้าผ่าน
    """
    current_user = get_current_user()
    _, subdomain = TenantManager.get_tenant_context()
    hospital = getattr(current_user, 'hospital', None) if current_user else None
    if not current_user or not hospital or hospital.subdomain != subdomain:
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))
    return None


# ============================ Patient: check-in ============================

@queue_bp.route('/checkin/<int:service_point_id>', methods=['GET', 'POST'])
def checkin(service_point_id):
    """หน้าเช็คอิน (เปิดจาก QR ที่จุดบริการ — QR encode service_point_id)"""
    sp = _service_point_or_404(service_point_id)

    if request.method == 'POST':
        name = (request.form.get('patient_name') or '').strip()
        phone = (request.form.get('patient_phone') or '').strip()
        booking_ref = (request.form.get('booking_reference') or '').strip()

        appointment_id = None
        if booking_ref:
            appt = (g.db.query(models.Appointment)
                    .filter_by(booking_reference=booking_ref).first())
            if appt is None:
                flash('ไม่พบรหัสการจองนี้ กรุณาตรวจสอบอีกครั้ง', 'error')
                return render_template('queue/checkin.html', service_point=sp)
            appointment_id = appt.id
            patient_ref = ids.resolve_patient_ref(appointment=appt, phone=phone, required=False)
            if patient_ref is None:
                flash('นัดนี้ยังไม่มีข้อมูลระบุตัวตนที่ใช้ผูกคิวได้ กรุณากรอกเบอร์โทรหรือแจ้งเจ้าหน้าที่', 'error')
                return render_template('queue/checkin.html', service_point=sp)
        elif phone:
            patient_ref = ids.resolve_patient_ref(phone=phone, required=False)
            if patient_ref is None:
                flash('เบอร์โทรศัพท์ไม่ถูกต้อง กรุณาตรวจสอบอีกครั้ง', 'error')
                return render_template('queue/checkin.html', service_point=sp)
        else:
            flash('กรุณากรอกเบอร์โทรศัพท์ หรือรหัสการจอง', 'error')
            return render_template('queue/checkin.html', service_point=sp)

        try:
            # check_in บังคับว่า นัดต้องตรงกับจุดบริการ/session ของจุดนี้ (กันสแกน QR ผิดจุด)
            result = qs.check_in(g.db, appointment_id, sp.id, patient_ref)
        except qs.ServicePointMismatch:
            flash('นัดนี้ไม่ได้อยู่ที่จุดบริการนี้ กรุณาตรวจสอบจุดบริการให้ถูกต้อง', 'error')
            return render_template('queue/checkin.html', service_point=sp)
        except gs.NoShowError:
            flash('นัดนี้เลยช่วงผ่อนผันแล้ว กรุณาติดต่อเจ้าหน้าที่เพื่อตรวจสอบหรือจองใหม่', 'error')
            return render_template('queue/checkin.html', service_point=sp)
        except ids.IdentityResolutionError:
            flash('ไม่สามารถระบุตัวตนสำหรับคิวนี้ได้ กรุณากรอกเบอร์โทรศัพท์หรือแจ้งเจ้าหน้าที่', 'error')
            return render_template('queue/checkin.html', service_point=sp)

        if isinstance(result, qs.ArrivalCheckInResult):
            return redirect(build_url_with_context(
                'queue.arrival',
                service_point_id=sp.id,
                appointment_id=result.appointment_id,
            ))
        qn.enqueue_checkin_confirm(g.tenant, result)
        return redirect(build_url_with_context('queue.ticket', entry_id=result.id))

    return render_template('queue/checkin.html', service_point=sp)


@queue_bp.route('/arrival/<int:service_point_id>/<int:appointment_id>')
def arrival(service_point_id, appointment_id):
    """ยืนยันการเช็คอินสำหรับนัดตามเวลา (ไม่ใช้คิว/ไม่ออกเลขคิว)"""
    sp = _service_point_or_404(service_point_id)
    appointment = g.db.query(models.Appointment).filter_by(id=appointment_id).first()
    if appointment is None:
        abort(404)
    return render_template('queue/arrival.html', appointment=appointment, service_point=sp)


@queue_bp.route('/ticket/<int:entry_id>')
def ticket(entry_id):
    """บัตรคิว (pull-based ฟรี) — ผู้รับบริการเปิดดูเลขคิว + จำนวนคิวก่อนหน้า"""
    entry = g.db.query(models.QueueEntry).filter_by(id=entry_id).first()
    if entry is None:
        abort(404)
    sp = g.db.query(models.ServicePoint).filter_by(id=entry.service_point_id).first()
    estimate = get_estimator(g.db).estimate(entry)
    return render_template('queue/ticket.html', entry=entry, service_point=sp,
                           estimate=estimate, ahead=estimate.people_ahead,
                           status_labels=STATUS_TH)


# ============================ Staff: console ============================

@queue_bp.route('/console/<int:service_point_id>')
@login_required
def console(service_point_id):
    denied = _deny_if_not_staff()
    if denied:
        return denied

    sp = _service_point_or_404(service_point_id)
    day = qs.today()
    base = (g.db.query(models.QueueEntry)
            .filter_by(service_point_id=sp.id, session_date=day))

    waiting = (base.filter(models.QueueEntry.status == 'checked_in')
               .order_by(models.QueueEntry.queue_number.asc()).all())
    serving = (base.filter(models.QueueEntry.status.in_(('called', 'in_service')))
               .order_by(models.QueueEntry.queue_number.asc()).all())
    done_count = base.filter(models.QueueEntry.status == 'done').count()

    return render_template('queue/console.html', service_point=sp, day=day,
                           waiting=waiting, serving=serving, done_count=done_count,
                           in_service_count=sum(1 for e in serving if e.status == 'in_service'),
                           status_labels=STATUS_TH)


@queue_bp.route('/console/<int:service_point_id>/call-next', methods=['POST'])
@login_required
def call_next(service_point_id):
    denied = _deny_if_not_staff()
    if denied:
        return denied

    sp = _service_point_or_404(service_point_id)
    # Phase 2: atomic priority pick+call (ratio/score + starvation + capacity)
    entry = ps.call_next(g.db, sp.id, qs.today(), actor='staff')
    if entry is None:
        flash('ไม่มีคิวที่รออยู่', 'info')
    else:
        qn.enqueue_queue_turn(g.tenant, entry)
        flash(f'เรียกคิวหมายเลข {entry.queue_number} แล้ว', 'success')
    return redirect(build_url_with_context('queue.console', service_point_id=sp.id))


@queue_bp.route('/entry/<int:entry_id>/<action>', methods=['POST'])
@login_required
def entry_action(entry_id, action):
    denied = _deny_if_not_staff()
    if denied:
        return denied

    to_status = _ACTION_TO_STATUS.get(action)
    if to_status is None:
        abort(404)

    entry = g.db.query(models.QueueEntry).filter_by(id=entry_id).first()
    if entry is None:
        abort(404)
    sp_id = entry.service_point_id          # เก็บก่อน transition (entry จะ expire หลัง commit)
    number = entry.queue_number

    try:
        qs.transition(g.db, entry_id, to_status, actor='staff')
    except qs.InvalidTransition:
        flash(f'คิวหมายเลข {number}: เปลี่ยนเป็น "{STATUS_TH[to_status]}" ไม่ได้ '
              f'(สถานะปัจจุบันไม่อนุญาต — อาจมีการกดซ้ำ)', 'warning')
        return redirect(build_url_with_context('queue.console', service_point_id=sp_id))

    flash(f'คิวหมายเลข {number}: {STATUS_TH[to_status]}', 'success')
    return redirect(build_url_with_context('queue.console', service_point_id=sp_id))


# ============================ จอแสดงคิว (TV) ============================

def _display_context(sp):
    day = qs.today()
    base = (g.db.query(models.QueueEntry)
            .filter_by(service_point_id=sp.id, session_date=day))
    now_serving = (base.filter(models.QueueEntry.status.in_(('called', 'in_service')))
                   .order_by(models.QueueEntry.called_at.desc().nullslast(),
                             models.QueueEntry.queue_number.asc()).all())
    waiting = (base.filter(models.QueueEntry.status == 'checked_in')
               .order_by(models.QueueEntry.queue_number.asc()).limit(12).all())
    return {'service_point': sp, 'now_serving': now_serving,
            'waiting': waiting, 'status_labels': STATUS_TH}


@queue_bp.route('/display/<int:service_point_id>')
def display(service_point_id):
    """จอแสดงคิวสำหรับเปิดบน TV (tenant-scoped, ไม่ต้อง login) — auto-refresh เฉพาะ display"""
    sp = _service_point_or_404(service_point_id)
    return render_template('queue/display.html', **_display_context(sp))


@queue_bp.route('/display/<int:service_point_id>/body')
def display_body(service_point_id):
    """fragment สำหรับ polling (display ล้วน — render server-side, JS แค่สลับ innerHTML)"""
    sp = _service_point_or_404(service_point_id)
    return render_template('queue/_display_body.html', **_display_context(sp))
