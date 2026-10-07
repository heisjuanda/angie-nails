"""Prueba el aviso de cita nueva sin levantar el Worker ni agendar una cita.

Lee `.dev.vars` y llama a CallMeBot (WhatsApp) y Resend (email) con el
mismo código que usa el Worker (`src/notify.py`), mostrando la respuesta
cruda de cada API. Si algo falla, el mensaje de la API dice por qué
(apikey inválida, número no activado, dominio sin verificar, etc.).

Uso:
    uv run python scripts/probe_notify.py

Las variables del entorno real tienen prioridad sobre `.dev.vars`, así que
también se puede probar así sin tocar el archivo:
    RESEND_API_KEY=re_xxx NOTIFY_EMAIL=angie@x.com uv run python scripts/probe_notify.py
"""

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import notify  # noqa: E402


def load_dev_vars(path: str = ".dev.vars") -> dict:
    env: dict = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


class FakeEnv:
    def __init__(self, values: dict):
        self._values = values

    def __getattr__(self, name):
        try:
            return self._values[name]
        except KeyError:
            raise AttributeError(name)


class _Resp:
    def __init__(self, response):
        self._r = response

    @property
    def ok(self):
        return self._r.is_success

    @property
    def status(self):
        return self._r.status_code

    async def json(self):
        return self._r.json()


class VerboseHttp:
    def __init__(self):
        self._client = httpx.AsyncClient(timeout=20)

    async def __call__(self, url, **kw):
        r = await self._client.request(
            kw.get("method") or "GET", url,
            headers=kw.get("headers"), content=kw.get("body"),
        )
        shown = url
        if "apikey=" in shown:
            shown = shown.split("&apikey=")[0] + "&apikey=***"
        print(f"  -> {kw.get('method') or 'GET'} {shown}")
        print(f"  <- {r.status_code} {r.text[:300]}")
        return _Resp(r)

    async def aclose(self):
        await self._client.aclose()


def _record() -> dict:
    return {
        "code": "AC-PROBA",
        "service_name": "Semipermanente",
        "date": date.today() + timedelta(days=2),
        "time": "10:00",
        "name": "Clienta de Prueba",
        "notes": "aviso de prueba",
    }


async def main() -> int:
    values = {**load_dev_vars(), **{k: v for k, v in __import__("os").environ.items()
                                    if k in {"CALLMEBOT_APIKEY", "NOTIFY_PHONE",
                                             "RESEND_API_KEY", "NOTIFY_EMAIL", "RESEND_FROM"}}}
    env = FakeEnv(values)
    record = _record()
    text = notify.messages.booking_whatsapp_text(record)

    whatsapp_on = bool(values.get("CALLMEBOT_APIKEY"))
    email_on = bool(values.get("RESEND_API_KEY") and values.get("NOTIFY_EMAIL"))
    print(f"WhatsApp (CallMeBot): {'activo' if whatsapp_on else 'SIN CONFIGURAR'}")
    if whatsapp_on:
        print(f"  destino: {values.get('NOTIFY_PHONE') or __import__('config').WHATSAPP}")
    print(f"Email (Resend): {'activo' if email_on else 'SIN CONFIGURAR'}")
    if email_on:
        print(f"  de: {values.get('RESEND_FROM') or notify.DEFAULT_FROM}")
        print(f"  para: {values['NOTIFY_EMAIL']}")
    if not whatsapp_on and not email_on:
        print("\nNo hay canales configurados. Descomenta las variables en .dev.vars.")
        return 1

    http = VerboseHttp()
    try:
        print("\n-- WhatsApp --")
        if whatsapp_on:
            ok = await notify.send_whatsapp(env, text, http=http)
            print("RESULTADO:", "ENVIADO" if ok else "NO ENVIADO")
        else:
            print("saltado")

        print("\n-- Email --")
        if email_on:
            ok = await notify.send_email(env, notify.booking_subject(record), text, http=http)
            print("RESULTADO:", "ENVIADO" if ok else "NO ENVIADO")
        else:
            print("saltado")
    finally:
        await http.aclose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
