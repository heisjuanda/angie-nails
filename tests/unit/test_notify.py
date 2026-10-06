import asyncio
import json
from datetime import date

import config
import notify


class FakeEnv:
    def __init__(self, **kw):
        self._kw = kw

    def __getattr__(self, name):
        try:
            return self._kw[name]
        except KeyError:
            raise AttributeError(name)


class FakeResponse:
    def __init__(self, ok=True, status=200, payload=None):
        self.ok = ok
        self.status = status
        self._payload = payload

    async def json(self):
        if self._payload is None:
            raise ValueError("no body")
        return self._payload


class RecordingHttp:
    def __init__(self, response=None):
        self.calls = []
        self._response = response or FakeResponse()

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self._response


def _run(coro):
    return asyncio.run(coro)


def _record() -> dict:
    return {
        "code": "AC-XXXXX",
        "service_name": "Semipermanente",
        "date": date(2026, 10, 10),
        "time": "08:00",
        "name": "Clienta de Prueba",
        "neighborhood": "San Fernando",
        "address": "Carrera 34 # 5-20",
        "notes": "",
    }


#  WhatsApp (CallMeBot)


def test_whatsapp_url_encodes_text_and_apikey():
    url = notify.whatsapp_url("573245967079", "Hola\nqué tal", "abc 123")
    assert url.startswith("https://api.callmebot.com/whatsapp.php?")
    assert "phone=573245967079" in url
    assert "text=Hola%0Aqu%C3%A9%20tal" in url
    assert "apikey=abc%20123" in url


def test_send_whatsapp_is_noop_without_apikey():
    http = RecordingHttp()
    assert _run(notify.send_whatsapp(FakeEnv(), "hola", http=http)) is False
    assert http.calls == []


def test_send_whatsapp_uses_notify_phone_or_default():
    http = RecordingHttp()
    assert _run(notify.send_whatsapp(FakeEnv(CALLMEBOT_APIKEY="k"), "hola", http=http)) is True
    assert "phone=" + config.WHATSAPP in http.calls[0][0][0]

    http = RecordingHttp()
    assert _run(notify.send_whatsapp(
        FakeEnv(CALLMEBOT_APIKEY="k", NOTIFY_PHONE="57300111222"), "hola", http=http
    )) is True
    assert "phone=57300111222" in http.calls[0][0][0]


def test_send_whatsapp_false_on_http_error():
    http = RecordingHttp(FakeResponse(ok=False, status=500))
    assert _run(notify.send_whatsapp(FakeEnv(CALLMEBOT_APIKEY="k"), "hola", http=http)) is False


def test_send_whatsapp_false_when_bot_reports_failure():
    http = RecordingHttp(FakeResponse(payload={"result": False, "error": "spam"}))
    assert _run(notify.send_whatsapp(FakeEnv(CALLMEBOT_APIKEY="k"), "hola", http=http)) is False


#  Email (Resend)


def test_send_email_is_noop_without_key_or_recipient():
    http = RecordingHttp()
    assert _run(notify.send_email(FakeEnv(), "s", "t", http=http)) is False
    assert _run(notify.send_email(FakeEnv(RESEND_API_KEY="k"), "s", "t", http=http)) is False
    assert _run(notify.send_email(FakeEnv(NOTIFY_EMAIL="a@b.co"), "s", "t", http=http)) is False
    assert http.calls == []


def test_send_email_posts_json_to_resend():
    http = RecordingHttp()
    ok = _run(notify.send_email(
        FakeEnv(RESEND_API_KEY="k", NOTIFY_EMAIL="angie@b.co", RESEND_FROM="AC <ac@b.co>"),
        "Nueva cita", "detalle", http=http,
    ))
    assert ok is True
    args, kwargs = http.calls[0]
    assert args[0] == "https://api.resend.com/emails"
    assert kwargs["method"] == "POST"
    assert kwargs["headers"]["authorization"] == "Bearer k"
    assert kwargs["headers"]["content-type"] == "application/json"
    assert json.loads(kwargs["body"]) == {
        "from": "AC <ac@b.co>", "to": "angie@b.co", "subject": "Nueva cita", "text": "detalle",
    }


def test_send_email_defaults_sender_to_resend_dev():
    http = RecordingHttp()
    _run(notify.send_email(
        FakeEnv(RESEND_API_KEY="k", NOTIFY_EMAIL="angie@b.co"), "s", "t", http=http
    ))
    body = json.loads(http.calls[0][1]["body"])
    assert body["from"] == notify.DEFAULT_FROM


def test_send_email_false_on_http_error():
    http = RecordingHttp(FakeResponse(ok=False, status=401))
    assert _run(notify.send_email(
        FakeEnv(RESEND_API_KEY="k", NOTIFY_EMAIL="a@b.co"), "s", "t", http=http
    )) is False


#  orquestación


def test_notify_booking_fires_both_channels():
    http = RecordingHttp()
    fired = _run(notify.notify_booking(
        FakeEnv(CALLMEBOT_APIKEY="k", RESEND_API_KEY="r", NOTIFY_EMAIL="angie@b.co"),
        _record(), http=http,
    ))
    assert fired == ["whatsapp", "email"]
    assert len(http.calls) == 2


def test_notify_booking_is_silent_noop_without_config():
    http = RecordingHttp()
    assert _run(notify.notify_booking(FakeEnv(), _record(), http=http)) == []
    assert http.calls == []


def test_notify_booking_isolates_channel_failures():
    calls = []

    async def flaky_whatsapp(*args, **kwargs):
        calls.append("whatsapp")
        raise OSError("network down")

    async def ok_email(*args, **kwargs):
        calls.append("email")
        return FakeResponse()

    class SplitHttp:
        async def __call__(self, url, **kwargs):
            if "callmebot" in url:
                return await flaky_whatsapp(url, **kwargs)
            return await ok_email(url, **kwargs)

    fired = _run(notify.notify_booking(
        FakeEnv(CALLMEBOT_APIKEY="k", RESEND_API_KEY="r", NOTIFY_EMAIL="angie@b.co"),
        _record(), http=SplitHttp(),
    ))
    assert fired == ["email"]
    assert calls == ["whatsapp", "email"]


def test_booking_subject_contains_code_service_and_time():
    subject = notify.booking_subject(_record())
    assert "AC-XXXXX" in subject
    assert "Semipermanente" in subject
    assert "8:00 a. m." in subject


def test_notify_booking_later_never_raises_outside_runtime():
    # Sin el runtime de Workers (import workers falla) no debe lanzar.
    notify.notify_booking_later(FakeEnv(), _record())
