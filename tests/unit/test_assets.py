import base64
import hashlib
import json
import os
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _build_steps() -> list[tuple[Path, Path, list[str]]]:
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    steps: list[tuple[Path, Path, list[str]]] = []
    for raw in pkg["scripts"]["build:assets"].split("&&"):
        parts = raw.strip().split()
        if not parts:
            continue
        bin_rel = f"{parts[0]}.cmd" if os.name == "nt" and (ROOT / f"{parts[0]}.cmd").exists() else parts[0]
        outfile = next(p.split("=", 1)[1] for p in parts if p.startswith("--outfile="))
        src = next(p for p in parts[1:] if not p.startswith("-"))
        cmd = [str(ROOT / bin_rel), *(p for p in parts[1:] if not p.startswith("--outfile="))]
        steps.append((ROOT / src, ROOT / outfile, cmd))
    return steps


def _parse_csp() -> dict[str, list[str]]:
    headers_text = (ROOT / "public" / "_headers").read_text(encoding="utf-8")
    for line in headers_text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("content-security-policy:"):
            raw_csp = stripped.split(":", 1)[1].strip()
            directives: dict[str, list[str]] = {}
            for part in raw_csp.split(";"):
                tokens = part.strip().split()
                if tokens:
                    directives[tokens[0].lower()] = tokens[1:]
            return directives
    raise AssertionError("No se encontró Content-Security-Policy en public/_headers")


class _CSPHTMLInspector(HTMLParser):
    def __init__(self, rel_path: str, csp: dict[str, list[str]]) -> None:
        super().__init__(convert_charrefs=False)
        self.rel_path = rel_path
        self.style_src = csp.get("style-src", csp.get("default-src", []))
        self.script_src = csp.get("script-src", csp.get("default-src", []))
        self.violations: list[str] = []
        self._active_tag: tuple[str, int, dict[str, str | None]] | None = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_l = tag.lower()
        attr_map = {k.lower(): v for k, v in attrs}
        line, _ = self.getpos()

        if "style" in attr_map and "'unsafe-inline'" not in self.style_src:
            self.violations.append(
                f"{self.rel_path}:{line} usa atributo inline style=\"...\" en <{tag_l}> bloqueado por style-src"
            )

        for attr_name in attr_map:
            if attr_name.startswith("on") and "'unsafe-inline'" not in self.script_src:
                self.violations.append(
                    f"{self.rel_path}:{line} usa manejador inline {attr_name}= en <{tag_l}> bloqueado por script-src"
                )

        if tag_l in ("style", "script"):
            self._active_tag = (tag_l, line, attr_map)
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._active_tag is not None:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._active_tag is None or tag.lower() != self._active_tag[0]:
            return
        tag_l, line, attr_map = self._active_tag
        content = "".join(self._buffer)
        self._active_tag = None
        self._buffer = []

        digest = base64.b64encode(hashlib.sha256(content.encode("utf-8")).digest()).decode("ascii")
        sha_token = f"'sha256-{digest}'"

        if tag_l == "style":
            if "'unsafe-inline'" not in self.style_src and sha_token not in self.style_src:
                self.violations.append(
                    f"{self.rel_path}:{line} contiene un bloque <style> inline bloqueado por style-src"
                )
        elif tag_l == "script" and "src" not in attr_map:
            script_type = (attr_map.get("type") or "").strip().lower()
            if script_type in ("application/ld+json", "application/json"):
                return
            if "'unsafe-inline'" not in self.script_src and sha_token not in self.script_src:
                self.violations.append(
                    f"{self.rel_path}:{line} contiene un <script> inline sin hash autorizado en script-src ({sha_token})"
                )


def _find_csp_violations(html_text: str, rel_path: str, csp: dict[str, list[str]]) -> list[str]:
    inspector = _CSPHTMLInspector(rel_path, csp)
    inspector.feed(html_text)
    return inspector.violations


def test_html_pages_comply_with_csp():
    """Ninguna página HTML en public/ debe incluir <style>, style="", on*= ni <script> bloqueados por la CSP."""
    csp = _parse_csp()
    assert "'unsafe-inline'" not in csp.get("style-src", []), "style-src no debe usar 'unsafe-inline'"
    assert "'unsafe-inline'" not in csp.get("script-src", []), "script-src no debe usar 'unsafe-inline'"

    html_files = sorted((ROOT / "public").rglob("*.html"))
    assert html_files, "No se encontraron archivos HTML en public/"

    all_violations: list[str] = []
    for html_path in html_files:
        rel = html_path.relative_to(ROOT).as_posix()
        all_violations.extend(_find_csp_violations(html_path.read_text(encoding="utf-8"), rel, csp))

    assert all_violations == [], "Violaciones de CSP detectadas en HTML:\n" + "\n".join(all_violations)


def test_csp_checker_detects_inline_styles_and_scripts():
    """El verificador de CSP debe atrapar bloques <style>, atributos style= y scripts inline no autorizados."""
    csp = _parse_csp()
    sample = """<!doctype html><html><head><style>.x{color:red}</style><script>alert(1)</script></head>
    <body style="margin:0" onclick=" evil() "><script type="application/ld+json">{"ok":true}</script></body></html>"""
    violations = _find_csp_violations(sample, "public/fake.html", csp)
    assert len(violations) == 4
    assert any("<style> inline" in v for v in violations)
    assert any("<script> inline" in v for v in violations)
    assert any('atributo inline style="..."' in v for v in violations)
    assert any("manejador inline onclick=" in v for v in violations)


def test_html_pages_only_load_minified_assets_from_build_script():
    """Todas las páginas HTML deben cargar solo .min.js/.min.css generados por build:assets."""
    built_outputs = {out.resolve() for _, out, _ in _build_steps()}
    html_files = sorted((ROOT / "public").rglob("*.html"))
    assert html_files, "No se encontraron archivos HTML en public/"

    asset_pattern = re.compile(
        r"""<(?:script[^>]+src|link[^>]+rel=["']stylesheet["'][^>]+href|link[^>]+href=["'][^"']+["'][^>]+rel=["']stylesheet["'])""",
        re.IGNORECASE,
    )
    url_pattern = re.compile(r"""(?:src|href)=["']([^"']+)["']""", re.IGNORECASE)

    for html_path in html_files:
        text = html_path.read_text(encoding="utf-8")
        for match in asset_pattern.finditer(text):
            tag = match.group(0)
            url_match = url_pattern.search(tag)
            if not url_match:
                continue
            raw_url = url_match.group(1)
            if raw_url.startswith(("http://", "https://", "//")):
                continue
            clean_path = raw_url.split("?", 1)[0].split("#", 1)[0].lstrip("/")
            assert clean_path.endswith((".min.js", ".min.css")), (
                f"{html_path.relative_to(ROOT)} referencia un asset sin minificar: {raw_url}"
            )
            disk_path = (ROOT / "public" / clean_path).resolve()
            assert disk_path.exists(), f"{html_path.relative_to(ROOT)} referencia un asset inexistente: {raw_url}"
            assert disk_path in built_outputs, (
                f"{html_path.relative_to(ROOT)} carga {raw_url}, pero no está en build:assets de package.json"
            )


def test_minified_assets_are_in_sync_with_sources():
    """Cada archivo .min.js y .min.css en disco debe coincidir byte a byte con su fuente compilada."""
    steps = _build_steps()
    assert len(steps) >= 7

    for src, out, cmd in steps:
        assert src.exists(), f"No existe el archivo fuente {src.relative_to(ROOT)}"
        assert out.exists(), f"No existe el archivo compilado {out.relative_to(ROOT)}"
        compiled = subprocess.check_output(cmd, cwd=ROOT)
        on_disk = out.read_bytes()
        assert on_disk == compiled, (
            f"{out.relative_to(ROOT)} está desincronizado respecto a {src.relative_to(ROOT)}. "
            f"Ejecuta `npm run build:assets`."
        )


def test_build_assets_recompiles_stale_minified_file():
    """build_assets() de conftest debe regenerar un .min.js desactualizado antes de correr E2E."""
    import conftest

    target = ROOT / "public" / "js" / "booking.min.js"
    original = target.read_bytes()
    try:
        target.write_bytes(b"/* stale */")
        assert target.read_bytes() != original
        conftest.build_assets()
        assert target.read_bytes() == original
    finally:
        if target.read_bytes() != original:
            target.write_bytes(original)

