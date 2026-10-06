"""Levanta el Worker real (wrangler dev) contra una D1 local aislada.

Se arrancan dos instancias en paralelo:
  - `server`: Turnstile de prueba que SIEMPRE aprueba.
  - `strict_server`: Turnstile de prueba que SIEMPRE rechaza (y se usa para
    el bloqueo por intentos fallidos, para no afectar al resto de pruebas).
Cada una tiene su propio directorio de persistencia y sus propios secretos.
"""

import contextlib
import hashlib
import json
import os
import secrets
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

import availability
import config
import mfa
from helpers import TEST_WINDOW_DAYS

ROOT = Path(__file__).resolve().parents[1]
NPX = "npx.cmd" if os.name == "nt" else "npx"
DB_NAME = "ac-luxury-db"
TURNSTILE_PASS = "1x0000000000000000000000000000000AA"
TURNSTILE_FAIL = "2x0000000000000000000000000000000AA"


WRANGLER_ENV = {**os.environ, "WRANGLER_SEND_METRICS": "false", "CI": "1"}


def _kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        else:
            # npx lanza sh → node → workerd. Matar solo a npx deja huérfanos que
            # siguen ocupando los puertos 8791/8792 con la D1 ya borrada debajo,
            # y la corrida siguiente termina hablándoles (500s sin sentido).
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                proc.kill()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        pass


def run_wrangler(args: list[str], timeout: float = 180) -> str:
    with tempfile.TemporaryFile("w+", encoding="utf-8") as out:
        proc = subprocess.Popen([NPX, "wrangler", *args], cwd=ROOT, stdin=subprocess.DEVNULL,
                                stdout=out, stderr=subprocess.STDOUT, env=WRANGLER_ENV)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            out.seek(0)
            raise TimeoutError(f"wrangler {' '.join(args[:3])} no terminó en {timeout}s:\n{out.read()[-2000:]}")
        out.seek(0)
        text = out.read()
    if proc.returncode != 0:
        raise RuntimeError(f"wrangler {' '.join(args[:3])} falló ({proc.returncode}):\n{text[-2000:]}")
    return text


@dataclass
class Instance:
    name: str
    port: int
    inspector_port: int
    turnstile_secret: str
    workdir: Path
    admin_password: str = field(default_factory=lambda: secrets.token_urlsafe(12))
    session_secret: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    totp_secret: str = ""   # vacío = panel sin segundo factor
    proc: subprocess.Popen | None = None
    log_path: Path | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def persist_dir(self) -> Path:
        return self.workdir / "state"

    def sql(self, command: str) -> list[dict]:
        """Ejecuta SQL directamente sobre la D1 local de esta instancia."""
        text = run_wrangler(["d1", "execute", DB_NAME, "--local", "--persist-to", str(self.persist_dir),
                             "--json", "--command", command], timeout=120)
        return json.loads(text[text.index("["):])[0]["results"]

    def prepare(self) -> None:
        """Escribe los secretos y crea la D1 local. Se hace antes de arrancar cualquier servidor."""
        self.workdir.mkdir(parents=True, exist_ok=True)
        env_file = self.workdir / ".env.test"
        env_file.write_text(
            "TURNSTILE_SITE_KEY=1x00000000000000000000AA\n"
            f"TURNSTILE_SECRET={self.turnstile_secret}\n"
            f"ADMIN_PASSWORD={self.admin_password}\n"
            f"SESSION_SECRET={self.session_secret}\n"
            f"TOTP_SECRET={self.totp_secret}\n"
            f"BOOKING_WINDOW_DAYS={TEST_WINDOW_DAYS}\n",
            encoding="utf-8",
        )
        run_wrangler(["d1", "migrations", "apply", DB_NAME, "--local", "--persist-to", str(self.persist_dir)])

    def start(self) -> None:
        env_file = self.workdir / ".env.test"
        self.log_path = self.workdir / "wrangler.log"
        log = open(self.log_path, "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [NPX, "wrangler", "dev", "--port", str(self.port), "--ip", "127.0.0.1",
             "--inspector-port", str(self.inspector_port), "--persist-to", str(self.persist_dir),
             "--env-file", str(env_file), "--show-interactive-dev-session=false", "--log-level", "log"],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            env=WRANGLER_ENV, start_new_session=True,
        )

    def wait_ready(self, timeout: float = 240) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"wrangler dev ({self.name}) terminó:\n{self.log_path.read_text(encoding='utf-8')[-3000:]}")
            try:
                if httpx.get(f"{self.base_url}/api/config", timeout=5).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(1)
        raise TimeoutError(f"wrangler dev ({self.name}) no respondió:\n{self.log_path.read_text(encoding='utf-8')[-3000:]}")

    def stop(self) -> None:
        if self.proc:
            _kill_tree(self.proc)

    def client(self, **kw) -> httpx.Client:
        headers = {"origin": self.base_url, **kw.pop("headers", {})}
        return httpx.Client(base_url=self.base_url, headers=headers, timeout=30, **kw)

    @contextlib.contextmanager
    def admin_client(self):
        with self.client() as c:
            r = c.post("/api/admin/login", json={"password": self.admin_password})
            assert r.status_code == 200, r.text
            if r.json().get("mfa_required"):
                r = c.post("/api/admin/mfa", json={"code": mfa.current_code(self.totp_secret)})
                assert r.status_code == 200, r.text
            yield c


def _open_days():
    today = availability.now_local().date()
    last = today + timedelta(days=TEST_WINDOW_DAYS - 1)
    d = today + timedelta(days=2)
    while d <= last:
        if config.BUSINESS_HOURS.get(d.weekday()):
            yield d
        d += timedelta(days=1)


@pytest.fixture(scope="session")
def _instances():
    base = Path(tempfile.mkdtemp(prefix="ac-it-"))
    instances = [
        Instance("server", 8791, 9331, TURNSTILE_PASS, base / "server", totp_secret=mfa.random_secret()),
        Instance("strict", 8792, 9332, TURNSTILE_FAIL, base / "strict"),
    ]
    try:
        for inst in instances:
            inst.prepare()
        for inst in instances:
            inst.start()
        for inst in instances:
            inst.wait_ready()
        yield {i.name: i for i in instances}
    finally:
        for inst in instances:
            inst.stop()
        for _ in range(10):
            shutil.rmtree(base, ignore_errors=True)
            if not base.exists():
                break
            time.sleep(0.5)


@pytest.fixture(scope="session")
def server(_instances) -> Instance:
    return _instances["server"]


@pytest.fixture(scope="session")
def strict_server(_instances) -> Instance:
    return _instances["strict"]


@pytest.fixture(scope="session")
def _day_pool():
    return _open_days()


@pytest.fixture
def free_day(_day_pool):
    try:
        return next(_day_pool)
    except StopIteration:
        pytest.fail("Se acabaron los días libres de la ventana de reserva para las pruebas.")


def _ip_para(nombre_test: str) -> str:
    """Una IP distinta por test, estable entre corridas.

    Cada test necesita su propio cubo en `booking_attempts`: si comparten 127.0.0.1 crean
    decenas de citas en menos de un minuto y el tope por IP los tumbaría a todos. Limpiar
    la tabla antes de cada test no sirve, porque `Instance.sql()` lanza un subproceso
    `wrangler` y cuesta unos 3 s. Esto no cuesta nada y además es más honesto: cada test
    simula una conexión distinta.
    """
    h = hashlib.sha256(nombre_test.encode()).hexdigest()
    return f"10.{int(h[:2], 16)}.{int(h[2:4], 16)}.{int(h[4:6], 16)}"


@pytest.fixture
def api(server, request):
    with server.client(headers={"cf-connecting-ip": _ip_para(request.node.name)}) as c:
        yield c


@pytest.fixture
def admin(server):
    with server.admin_client() as c:
        yield c
