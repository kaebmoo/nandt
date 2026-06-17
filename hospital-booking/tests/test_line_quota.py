"""LINE push-quota remaining (Phase 5.3, second half)."""

from flask_app.app.services import analytics_service as a


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


class _FakeLine:
    def __init__(self, quota, consumption):
        self._quota = quota
        self._consumption = consumption

    def get(self, url, **_):
        return _Resp(self._quota) if url.endswith("/quota") else _Resp(self._consumption)


def test_line_quota_limited_computes_remaining():
    client = _FakeLine({"type": "limited", "value": 1000}, {"totalUsage": 300})
    assert a._line_quota_from_api("tok", client) == {
        "type": "limited", "limit": 1000, "used": 300, "remaining": 700,
    }


def test_line_quota_unlimited_plan_has_no_counts():
    client = _FakeLine({"type": "none"}, {})
    result = a._line_quota_from_api("tok", client)
    assert result["type"] == "none" and result["remaining"] is None


def test_line_quota_remaining_never_negative():
    client = _FakeLine({"type": "limited", "value": 500}, {"totalUsage": 900})
    assert a._line_quota_from_api("tok", client)["remaining"] == 0


def test_line_quota_http_error_is_unavailable():
    class _Err:
        def get(self, url, **_):
            return _Resp({"message": "Authentication failed"}, status=401)

    assert a._line_quota_from_api("tok", _Err()) is None
