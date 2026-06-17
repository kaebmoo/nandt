"""Per-IP fixed-window throttle for the public (no-auth) check-in POST."""

from flask_app.app import queue_routes as qr


class _FakeRedis:
    def __init__(self):
        self.counts = {}
        self.expires = {}

    def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def expire(self, key, window):
        self.expires[key] = window


def test_rate_limited_flips_after_limit():
    r = _FakeRedis()
    # limit=3 → the 4th and 5th hits in the window are throttled
    results = [qr._rate_limited(r, 'checkin_rl:1:1.2.3.4', 3, 60) for _ in range(5)]
    assert results == [False, False, False, True, True]
    # TTL is set exactly once (on the first hit) — not reset every incr, or the
    # window would never roll over.
    assert r.expires == {'checkin_rl:1:1.2.3.4': 60}
