"""Channel entry links for QR/check-in surfaces (Phase 4.5 / 4.10)."""

from __future__ import annotations

from urllib.parse import quote, urlencode


def _base(public_base_url: str) -> str:
    return (public_base_url or "").rstrip("/")


def web_checkin_url(public_base_url: str, service_point_id: int, *, subdomain: str | None = None) -> str:
    url = f"{_base(public_base_url)}/queue/checkin/{int(service_point_id)}"
    if subdomain:
        return f"{url}?{urlencode({'subdomain': subdomain})}"
    return url


def line_liff_checkin_url(config, public_base_url: str, service_point_id: int,
                          *, subdomain: str | None = None) -> str | None:
    liff_id = getattr(config, "line_liff_id", None)
    if not liff_id:
        return None
    checkin_url = web_checkin_url(public_base_url, service_point_id, subdomain=subdomain)
    params = {
        "service_point_id": int(service_point_id),
        "checkin_url": checkin_url,
    }
    return f"https://liff.line.me/{quote(str(liff_id), safe='')}?{urlencode(params)}"


def telegram_checkin_url(config, service_point_id: int) -> str | None:
    username = getattr(config, "telegram_bot_username", None)
    if not username:
        return None
    start_param = f"sp_{int(service_point_id)}"
    short_name = getattr(config, "telegram_mini_app_short_name", None)
    if short_name:
        return (
            f"https://t.me/{quote(str(username), safe='')}/"
            f"{quote(str(short_name), safe='')}?{urlencode({'startapp': start_param})}"
        )
    return f"https://t.me/{quote(str(username), safe='')}?{urlencode({'start': start_param})}"


def build_checkin_links(config, public_base_url: str, service_point_id: int,
                        *, subdomain: str | None = None) -> dict:
    links = {
        "web": web_checkin_url(public_base_url, service_point_id, subdomain=subdomain),
        "line_liff": line_liff_checkin_url(
            config,
            public_base_url,
            service_point_id,
            subdomain=subdomain,
        ),
        "telegram": telegram_checkin_url(config, service_point_id),
    }
    return {key: value for key, value in links.items() if value}
