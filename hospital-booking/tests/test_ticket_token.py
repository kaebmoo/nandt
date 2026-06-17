"""Signed, tenant-bound ticket tokens replace the enumerable numeric entry_id."""

from flask_app.app import queue_routes as qr


def test_ticket_token_roundtrip_and_tenant_binding():
    token = qr.make_ticket_token(42, 'tenant_humnoi')

    # valid token for the same tenant resolves back to the entry id
    assert qr.read_ticket_token(token, 'tenant_humnoi') == 42

    # a token minted for another tenant is rejected (no cross-tenant reuse)
    assert qr.read_ticket_token(token, 'tenant_other') is None

    # tampered / garbage tokens are rejected, never raise
    assert qr.read_ticket_token(token + 'x', 'tenant_humnoi') is None
    assert qr.read_ticket_token('garbage', 'tenant_humnoi') is None

    # tokens are not the bare id (enumeration is the whole point of this)
    assert str(42) not in token
