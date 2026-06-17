from shared_db import models
from flask_app.app.services import messaging_links


def test_build_checkin_links_includes_web_and_configured_channels():
    cfg = models.MessagingConfig(
        line_liff_id="2000000000-AbCdEf",
        telegram_bot_username="nuddee_test_bot",
        telegram_mini_app_short_name="checkin",
    )

    links = messaging_links.build_checkin_links(
        cfg,
        "https://humnoi.example.com/",
        12,
        subdomain="humnoi",
    )

    assert links == {
        "web": "https://humnoi.example.com/queue/checkin/12?subdomain=humnoi",
        "line_liff": (
            "https://liff.line.me/2000000000-AbCdEf?service_point_id=12&"
            "checkin_url=https%3A%2F%2Fhumnoi.example.com%2Fqueue%2Fcheckin%2F12%3Fsubdomain%3Dhumnoi"
        ),
        "telegram": "https://t.me/nuddee_test_bot/checkin?startapp=sp_12",
    }


def test_telegram_checkin_url_falls_back_to_bot_deep_link_without_short_name():
    cfg = models.MessagingConfig(telegram_bot_username="nuddee_test_bot")

    assert messaging_links.telegram_checkin_url(cfg, 5) == (
        "https://t.me/nuddee_test_bot?start=sp_5"
    )


def test_unconfigured_channel_links_are_omitted():
    links = messaging_links.build_checkin_links(None, "https://example.com", 7)

    assert links == {"web": "https://example.com/queue/checkin/7"}
