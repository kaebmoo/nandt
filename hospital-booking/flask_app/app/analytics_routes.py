"""Analytics dashboard routes (Phase 5)."""

import datetime

from flask import Blueprint, abort, flash, g, redirect, render_template, request

from .auth import get_current_user, login_required
from .core.tenant_manager import TenantManager
from .services import analytics_service
from .utils.url_helper import build_url_with_context

analytics_bp = Blueprint('analytics', __name__, url_prefix='/analytics')


def _deny_if_not_staff():
    current_user = get_current_user()
    _, subdomain = TenantManager.get_tenant_context()
    hospital = getattr(current_user, 'hospital', None) if current_user else None
    if not current_user or not hospital or hospital.subdomain != subdomain:
        flash('ไม่สามารถเข้าถึงได้', 'error')
        return redirect(build_url_with_context('main.index'))
    return None


def _parse_date(value, fallback):
    if not value:
        return fallback
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        abort(400)


@analytics_bp.route('/')
@login_required
def index():
    denied = _deny_if_not_staff()
    if denied:
        return denied

    today = datetime.date.today()
    date_to = _parse_date(request.args.get('to'), today)
    date_from = _parse_date(request.args.get('from'), date_to - datetime.timedelta(days=6))

    queue = analytics_service.queue_summary(g.db, date_from, date_to)
    messaging = analytics_service.message_cost_summary(g.db, date_from, date_to)
    line_quota = analytics_service.line_message_quota(g.db)  # best-effort; None if LINE off/down

    return render_template(
        'analytics/index.html',
        date_from=date_from,
        date_to=date_to,
        queue=queue,
        messaging=messaging,
        line_quota=line_quota,
    )
