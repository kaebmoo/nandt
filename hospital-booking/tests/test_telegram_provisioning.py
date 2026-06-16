import pytest

from shared_db import crypto, models
from flask_app.app.services import telegram_provisioning as tp


class FakeResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data


class FakeTelegramHttp:
    def __init__(self, usernames=None, fail_method=None, fail_description="Unauthorized"):
        self.usernames = list(usernames or ["nuddee_test_bot"])
        self.fail_method = fail_method
        self.fail_description = fail_description
        self.calls = []

    def post(self, url, json, timeout):
        method = url.rsplit("/", 1)[-1]
        self.calls.append({"method": method, "url": url, "json": json, "timeout": timeout})
        if method == self.fail_method:
            return FakeResponse({"ok": False, "description": self.fail_description}, status_code=401)
        if method == "getMe":
            username = self.usernames.pop(0) if self.usernames else "nuddee_test_bot"
            return FakeResponse({"ok": True, "result": {"id": 1001, "username": username}})
        return FakeResponse({"ok": True, "result": True})


class RaisingTelegramHttp:
    def post(self, url, json, timeout):
        raise tp.requests.ConnectionError(f"connect failed for {url}")


@pytest.fixture()
def messaging_key(monkeypatch):
    monkeypatch.setenv(crypto.ENV_KEY, crypto.generate_key())


def _config_count(db):
    return db.query(models.MessagingConfig).count()


def _config(db):
    return db.query(models.MessagingConfig).one()


def test_provision_telegram_bot_encrypts_token_and_registers_bot_api(db, messaging_key):
    http = FakeTelegramHttp()

    result = tp.provision_telegram_bot(
        db,
        "tenant_humnoi",
        "123456:plain-secret-token",
        "tenant",
        "https://humnoi.example.com",
        mini_app_short_name="nuddee",
        web_app_url="https://humnoi.example.com/mini",
        webhook_secret="abc_DEF-123",
        http_client=http,
    )

    assert result == {
        "status": "active",
        "bot_username": "nuddee_test_bot",
        "ownership": "tenant",
        "webhook_url": "https://humnoi.example.com/webhooks/telegram/tenant_humnoi",
        "mini_app_short_name": "nuddee",
    }
    assert [c["method"] for c in http.calls] == [
        "getMe",
        "setWebhook",
        "setChatMenuButton",
        "setMyCommands",
    ]
    webhook_payload = http.calls[1]["json"]
    assert webhook_payload["secret_token"] == "abc_DEF-123"
    assert webhook_payload["allowed_updates"] == ["message", "callback_query", "my_chat_member"]
    menu_payload = http.calls[2]["json"]
    assert menu_payload["menu_button"]["web_app"]["url"] == "https://humnoi.example.com/mini"

    cfg = _config(db)
    assert cfg.telegram_status == "active"
    assert cfg.telegram_last_error is None
    assert cfg.telegram_bot_username == "nuddee_test_bot"
    assert cfg.telegram_bot_ownership == "tenant"
    assert cfg.telegram_mini_app_short_name == "nuddee"
    assert cfg.telegram_bot_token_enc != "123456:plain-secret-token"
    assert cfg.telegram_webhook_secret_enc != "abc_DEF-123"
    assert crypto.decrypt(cfg.telegram_bot_token_enc) == "123456:plain-secret-token"
    assert crypto.decrypt(cfg.telegram_webhook_secret_enc) == "abc_DEF-123"


def test_provision_telegram_bot_marks_error_without_storing_invalid_token(db, messaging_key):
    http = FakeTelegramHttp(fail_method="getMe", fail_description="Unauthorized")

    with pytest.raises(tp.TelegramProvisioningError):
        tp.provision_telegram_bot(
            db,
            "tenant_humnoi",
            "bad-token",
            "tenant",
            "https://humnoi.example.com",
            http_client=http,
        )

    cfg = _config(db)
    assert cfg.telegram_status == "error"
    assert cfg.telegram_last_error == "Unauthorized"
    assert cfg.telegram_bot_token_enc is None
    assert cfg.telegram_webhook_secret_enc is None


def test_provision_telegram_bot_redacts_token_from_transport_errors(db, messaging_key):
    token = "999888:SUPER-SECRET-DONOTLOG"

    with pytest.raises(tp.TelegramProvisioningError) as excinfo:
        tp.provision_telegram_bot(
            db,
            "tenant_humnoi",
            token,
            "tenant",
            "https://humnoi.example.com",
            http_client=RaisingTelegramHttp(),
        )

    cfg = _config(db)
    assert cfg.telegram_status == "error"
    assert cfg.telegram_last_error == "Telegram API request failed"
    assert token not in cfg.telegram_last_error
    assert token not in str(excinfo.value)
    assert "bot999888:SUPER-SECRET-DONOTLOG" not in cfg.telegram_last_error
    assert cfg.telegram_bot_token_enc is None
    assert cfg.telegram_webhook_secret_enc is None


def test_safe_error_redacts_telegram_tokens():
    token = "999888:SUPER-SECRET-DONOTLOG"
    message = f"failed https://api.telegram.org/bot{token}/getMe and bare {token}"

    redacted = tp._safe_error(message)

    assert token not in redacted
    assert "bot999888:SUPER-SECRET-DONOTLOG" not in redacted
    assert "bot<redacted>" in redacted


def test_reprovision_telegram_bot_updates_existing_config_row(db, messaging_key):
    first_http = FakeTelegramHttp(usernames=["first_bot"])
    second_http = FakeTelegramHttp(usernames=["second_bot"])

    tp.provision_telegram_bot(
        db,
        "tenant_humnoi",
        "111:first-token",
        "saas",
        "https://humnoi.example.com",
        webhook_secret="first_secret",
        http_client=first_http,
    )
    tp.provision_telegram_bot(
        db,
        "tenant_humnoi",
        "222:second-token",
        "tenant",
        "https://humnoi.example.com",
        webhook_secret="second_secret",
        http_client=second_http,
    )

    assert _config_count(db) == 1
    cfg = _config(db)
    assert cfg.telegram_status == "active"
    assert cfg.telegram_bot_username == "second_bot"
    assert cfg.telegram_bot_ownership == "tenant"
    assert crypto.decrypt(cfg.telegram_bot_token_enc) == "222:second-token"
    assert crypto.decrypt(cfg.telegram_webhook_secret_enc) == "second_secret"
