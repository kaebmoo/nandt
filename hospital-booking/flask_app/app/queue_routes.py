# flask_app/app/queue_routes.py
"""
Routes ของระบบคิว (Phase 1): check-in (patient), staff console, จอแสดงคิว.

Flask-first: business logic อยู่ที่ services/queue_service.py — routes นี้แค่ orchestrate + render Jinja2.
g.db ถูกตั้ง search_path ไป tenant schema แล้วโดย before_request middleware
"""

import os

import redis as _redis_lib
from flask import Blueprint, render_template, request, flash, redirect, abort, g, jsonify
from itsdangerous import BadSignature, URLSafeSerializer

from .auth import login_required, get_current_user
from .core.tenant_manager import TenantManager
from .utils.url_helper import build_url_with_context
from .services import grace_service as gs
from .services import identity_service as ids
from .services import messaging_identity as mi
from .services import messaging_links
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


def _ticket_serializer():
    secret = os.environ.get('SECRET_KEY', 'a-dev-secret-key')
    return URLSafeSerializer(secret, salt='queue-ticket')


def make_ticket_token(entry_id, tenant):
    """Unguessable, tenant-bound handle for a queue entry's ticket URL.

    Replaces the enumerable numeric entry_id so nobody can guess a ticket URL to
    view someone's queue status or (worse) bind their own push subscription to
    another patient's notifications via the pwa-subscription POST.
    """
    # ponytail: no expiry — the token only de-enumerates; the entry's own
    # status/date bounds its usefulness and a leaked token exposes one entry.
    return _ticket_serializer().dumps([str(tenant or ''), int(entry_id)])


def read_ticket_token(token, tenant):
    """Return the entry_id from a valid token for this tenant, else None."""
    try:
        scope, entry_id = _ticket_serializer().loads(token)
    except (BadSignature, ValueError, TypeError):
        return None
    if scope != str(tenant or ''):      # reject tokens minted for another tenant
        return None
    return int(entry_id)


_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = _redis_lib.from_url(
            os.environ.get('REDIS_URL', 'redis://localhost:6379/0'))
    return _redis_client


def _rate_limited(redis_client, key, limit, window):
    """Fixed-window counter: True once `key` is hit more than `limit` times per `window` s."""
    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, window)
    return count > limit


def _client_ip():
    fwd = request.headers.get('X-Forwarded-For', '')
    return fwd.split(',')[0].strip() or request.remote_addr or 'unknown'


def _too_many_checkins(sp_id):
    """Per-IP throttle for the public, no-auth check-in POST (anti walk-in spam).

    ponytail: Redis fixed window, fail-OPEN if Redis is down — never block a real
    patient on an infra hiccup. Per-IP is coarse: a clinic behind one NAT shares the
    budget, so keep the default generous and tune CHECKIN_RATE_* (or add a
    per-booking-reference / CAPTCHA check) if NAT collisions bite at a busy counter.
    """
    limit = int(os.environ.get('CHECKIN_RATE_LIMIT', '20'))
    window = int(os.environ.get('CHECKIN_RATE_WINDOW', '60'))
    try:
        return _rate_limited(_get_redis(), f'checkin_rl:{sp_id}:{_client_ip()}', limit, window)
    except Exception:
        return False


def _service_point_or_404(sp_id):
    sp = g.db.query(models.ServicePoint).filter_by(id=sp_id).first()
    if sp is None:
        abort(404)
    return sp


def _messaging_config():
    # messaging_config lives only in tenant schemas; with no tenant bound g.db is on
    # public, so querying it would 500 ("relation does not exist"). Callers treat
    # None as "not configured" (e.g. /queue/enter opened without ?subdomain=).
    if not getattr(g, 'tenant', None):
        return None
    return (g.db.query(models.MessagingConfig)
            .order_by(models.MessagingConfig.id.asc()).first())


def _render_checkin(sp):
    return render_template(
        'queue/checkin.html',
        service_point=sp,
        messaging_config=_messaging_config(),
        channel_auth_url=build_url_with_context('queue.channel_auth'),
    )


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

@queue_bp.route('/channel-auth', methods=['POST'])
def channel_auth():
    """Link a verified Mini App/PWA identity to a server-resolved patient_ref."""
    payload = request.get_json(silent=True) or {}
    channel = (payload.get('channel') or '').strip().lower()
    config = _messaging_config()

    try:
        if channel == 'line':
            link = mi.link_line_identity(
                g.db,
                config=config,
                id_token=payload.get('idToken'),
                booking_reference=payload.get('booking_reference'),
                patient_phone=payload.get('patient_phone'),
            )
        elif channel == 'telegram':
            link = mi.link_telegram_identity(
                g.db,
                config=config,
                init_data=payload.get('initData'),
                booking_reference=payload.get('booking_reference'),
                patient_phone=payload.get('patient_phone'),
            )
        elif channel == 'pwa':
            link = mi.link_pwa_subscription(
                g.db,
                subscription=payload.get('subscription'),
                booking_reference=payload.get('booking_reference'),
                patient_phone=payload.get('patient_phone'),
            )
        else:
            return jsonify({'linked': False, 'error': 'unsupported_channel'}), 400
    except (mi.LineIdTokenError, mi.InitDataValidationError) as exc:
        g.db.rollback()
        return jsonify({'linked': False, 'error': str(exc)}), 403
    except mi.ChannelIdentityError as exc:
        g.db.rollback()
        return jsonify({'linked': False, 'error': str(exc)}), 400

    return jsonify({
        'linked': True,
        'channel': link.channel,
    })

@queue_bp.route('/checkin/<int:service_point_id>', methods=['GET', 'POST'])
def checkin(service_point_id):
    """หน้าเช็คอิน (เปิดจาก QR ที่จุดบริการ — QR encode service_point_id)"""
    sp = _service_point_or_404(service_point_id)

    if request.method == 'POST':
        if _too_many_checkins(sp.id):
            flash('มีการเช็คอินบ่อยเกินไป กรุณารอสักครู่แล้วลองใหม่อีกครั้ง', 'error')
            return _render_checkin(sp), 429
        name = (request.form.get('patient_name') or '').strip()
        phone = (request.form.get('patient_phone') or '').strip()
        booking_ref = (request.form.get('booking_reference') or '').strip()

        appointment_id = None
        if booking_ref:
            appt = (g.db.query(models.Appointment)
                    .filter_by(booking_reference=booking_ref).first())
            if appt is None:
                flash('ไม่พบรหัสการจองนี้ กรุณาตรวจสอบอีกครั้ง', 'error')
                return _render_checkin(sp)
            appointment_id = appt.id
            patient_ref = ids.resolve_patient_ref(appointment=appt, phone=phone, required=False)
            if patient_ref is None:
                flash('นัดนี้ยังไม่มีข้อมูลระบุตัวตนที่ใช้ผูกคิวได้ กรุณากรอกเบอร์โทรหรือแจ้งเจ้าหน้าที่', 'error')
                return _render_checkin(sp)
        else:
            # walk-in: ใช้เบอร์ถ้ากรอก ไม่งั้นออก anon:{token} (technical fallback ตาม §4.6.1
            # — ไม่บล็อกคนเดินเข้าที่ไม่ให้เบอร์; ผูก channel ภายหลังได้ผ่าน ticket)
            patient_ref = ids.resolve_patient_ref(phone=phone, allow_anon=True)

        try:
            # check_in บังคับว่า นัดต้องตรงกับจุดบริการ/session ของจุดนี้ (กันสแกน QR ผิดจุด)
            result = qs.check_in(g.db, appointment_id, sp.id, patient_ref)
        except qs.ServicePointMismatch:
            flash('นัดนี้ไม่ได้อยู่ที่จุดบริการนี้ กรุณาตรวจสอบจุดบริการให้ถูกต้อง', 'error')
            return _render_checkin(sp)
        except gs.NoShowError:
            flash('นัดนี้เลยช่วงผ่อนผันแล้ว กรุณาติดต่อเจ้าหน้าที่เพื่อตรวจสอบหรือจองใหม่', 'error')
            return _render_checkin(sp)
        except ids.IdentityResolutionError:
            flash('ไม่สามารถระบุตัวตนสำหรับคิวนี้ได้ กรุณากรอกเบอร์โทรศัพท์หรือแจ้งเจ้าหน้าที่', 'error')
            return _render_checkin(sp)

        if isinstance(result, qs.ArrivalCheckInResult):
            return redirect(build_url_with_context(
                'queue.arrival',
                service_point_id=sp.id,
                appointment_id=result.appointment_id,
            ))
        ticket_token = make_ticket_token(result.id, g.tenant)
        qn.enqueue_checkin_confirm(g.tenant, result, url=build_url_with_context(
            'queue.ticket', token=ticket_token, _external=True))
        return redirect(build_url_with_context(
            'queue.ticket', token=ticket_token, checkin_confirm=1))

    return _render_checkin(sp)


@queue_bp.route('/enter')
def enter():
    """Mini App / LIFF entry router (Phase 4.5/4.10 deep-link consumer).

    Set this URL as the Telegram Mini App (BotFather /newapp) and the LINE LIFF
    endpoint. queue_mini_app.js reads the deep-link param — Telegram `startapp=sp_<id>`
    (arrives as `tgWebAppStartParam`) or LINE `service_point_id` / `checkin_url` — and
    forwards to that service point's check-in page; with no param it falls back home.
    LINE delivers its params inside liff.state, so the page needs the LIFF id to run
    liff.init() and resolve them.
    """
    config = _messaging_config()
    return render_template('queue/enter.html',
                           default_url=build_url_with_context('main.index'),
                           line_liff_id=getattr(config, 'line_liff_id', None) if config else None)


@queue_bp.route('/arrival/<int:service_point_id>/<int:appointment_id>')
def arrival(service_point_id, appointment_id):
    """ยืนยันการเช็คอินสำหรับนัดตามเวลา (ไม่ใช้คิว/ไม่ออกเลขคิว)"""
    sp = _service_point_or_404(service_point_id)
    appointment = g.db.query(models.Appointment).filter_by(id=appointment_id).first()
    if appointment is None:
        abort(404)
    return render_template('queue/arrival.html', appointment=appointment, service_point=sp)


@queue_bp.route('/ticket/<token>')
def ticket(token):
    """บัตรคิว (pull-based ฟรี) — ผู้รับบริการเปิดดูเลขคิว + จำนวนคิวก่อนหน้า"""
    entry_id = read_ticket_token(token, g.tenant)
    if entry_id is None:
        abort(404)
    entry = g.db.query(models.QueueEntry).filter_by(id=entry_id).first()
    if entry is None:
        abort(404)
    sp = g.db.query(models.ServicePoint).filter_by(id=entry.service_point_id).first()
    estimate = get_estimator(g.db).estimate(entry)
    return render_template('queue/ticket.html', entry=entry, service_point=sp,
                           estimate=estimate, ahead=estimate.people_ahead,
                           status_labels=STATUS_TH,
                           messaging_config=_messaging_config(),
                           checkin_confirm=request.args.get('checkin_confirm') == '1',
                           pwa_subscribe_url=build_url_with_context(
                               'queue.ticket_pwa_subscription',
                               token=token,
                           ),
                           service_worker_url=build_url_with_context('pwa.service_worker'))


@queue_bp.route('/ticket/<token>/pwa-subscription', methods=['POST'])
def ticket_pwa_subscription(token):
    """Store a browser push subscription for the patient who owns this ticket."""
    entry_id = read_ticket_token(token, g.tenant)
    if entry_id is None:
        abort(404)
    entry = g.db.query(models.QueueEntry).filter_by(id=entry_id).first()
    if entry is None:
        abort(404)
    config = _messaging_config()
    if not config or config.pwa_status != 'active' or not config.pwa_vapid_public_key:
        return jsonify({'linked': False, 'error': 'pwa_not_configured'}), 400

    payload = request.get_json(silent=True) or {}
    try:
        link = mi.link_pwa_subscription_for_patient_ref(
            g.db,
            subscription=payload.get('subscription') or payload,
            patient_ref=entry.patient_ref,
        )
    except mi.ChannelIdentityError as exc:
        g.db.rollback()
        return jsonify({'linked': False, 'error': str(exc)}), 400
    return jsonify({'linked': True, 'channel': link.channel})


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
    messaging_config = _messaging_config()
    checkin_links = messaging_links.build_checkin_links(
        messaging_config,
        request.url_root,
        sp.id,
        subdomain=g.subdomain,
    )

    return render_template('queue/console.html', service_point=sp, day=day,
                           waiting=waiting, serving=serving, done_count=done_count,
                           in_service_count=sum(1 for e in serving if e.status == 'in_service'),
                           status_labels=STATUS_TH,
                           checkin_links=checkin_links)


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
        qn.enqueue_queue_turn(g.tenant, entry, url=build_url_with_context(
            'queue.ticket', token=make_ticket_token(entry.id, g.tenant), _external=True))
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
