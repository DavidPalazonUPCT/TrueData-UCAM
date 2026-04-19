"""onboard_client_v2.py — provisioning pipeline v2 para clientes de la plataforma.

Invocar explícitamente con Python 3.9+: `python3 deploy/onboard_client_v2.py ...`
en Linux/macOS o `py deploy\\onboard_client_v2.py ...` en Windows. Sin shebang:
en Windows el `py.exe` launcher podía delegar a un `python3.exe` alias roto de
Microsoft Store y provocar `ModuleNotFoundError` espurios.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

import requests
from dotenv import find_dotenv, load_dotenv

# Ensure repo root is on sys.path so `deploy.*` is importable when this script
# is invoked directly (python3 deploy/onboard_client_v2.py …) rather than via
# `python -m deploy.onboarding`.
_REPO_ROOT_FOR_PATH = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT_FOR_PATH) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_PATH))

from deploy.onboarding.manifest import ManifestError, load_manifest  # noqa: E402
from deploy.onboarding.secrets import (  # noqa: E402
    ENV_TEMPLATE,
    GATEWAY_ENV_TEMPLATE,
    render_env,
    write_atomic,
    write_secrets,
)
from deploy.onboarding.smoke import SmokeError, smoke_tests  # noqa: E402
from deploy.onboarding.tb import (  # noqa: E402
    ExternalError, HTTP_TIMEOUT, REQUIRED_PROFILES,
    _auth_headers,
    tb_list_profiles, tb_create_profile, ensure_profiles,
    tb_get_device_by_name, tb_create_device, tb_ensure_additional_info,
    tb_get_credentials, tb_rotate_credentials,
    ensure_writeback_devices, ensure_gateway_device,
    tb_login,
)

# Carga `.env` desde la raíz del repo (o cualquier ancestor) al entorno del
# proceso. Variables ya seteadas en el shell ganan: load_dotenv no sobrescribe
# por default, lo que permite CI/CD inyectar credenciales sin tocar .env.
load_dotenv(find_dotenv(usecwd=True))

# Raíz del repo (dos niveles arriba del script): se usa como cwd al invocar
# `docker compose` desde los auto-start helpers.
REPO_ROOT = Path(__file__).resolve().parent.parent

# ============================================================================
# Exit codes (spec §6.4)
# ============================================================================
EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_BAD_INPUT = 2
EXIT_EXTERNAL = 3
EXIT_SMOKE_FAILED = 4


# ============================================================================
# Env vars (spec §6.3)
# ============================================================================

DEFAULT_TB_URL = "http://localhost:9090"
DEFAULT_TB_USER = "tenant@thingsboard.org"
DEFAULT_NR_URL = "http://localhost:1880"
DEFAULT_NR_DATA_DIR = "truedata-nodered/data"
DEFAULT_NR_CREDENTIAL_SECRET = "platform"  # see truedata-nodered/settings.js


def read_env() -> dict:
    """Read TB_* and NR_* from environment.

    Returns dict with tb_url, tb_user, tb_password, nr_url, nr_data_dir,
    nr_credential_secret. Raises RuntimeError if TB_ADMIN_PASSWORD is not set.
    """
    password = os.environ.get("TB_ADMIN_PASSWORD")
    if not password:
        raise RuntimeError("env: TB_ADMIN_PASSWORD is required (not set)")
    return {
        "tb_url": os.environ.get("TB_URL", DEFAULT_TB_URL).rstrip("/"),
        "tb_user": os.environ.get("TB_ADMIN_USER", DEFAULT_TB_USER),
        "tb_password": password,
        "nr_url": os.environ.get("NR_URL", DEFAULT_NR_URL).rstrip("/"),
        "nr_data_dir": os.environ.get("NR_DATA_DIR", DEFAULT_NR_DATA_DIR),
        "nr_credential_secret": os.environ.get("NODE_RED_CREDENTIAL_SECRET", DEFAULT_NR_CREDENTIAL_SECRET),
    }


# ============================================================================
# Runtime config for NR function flow
# ============================================================================


NR_RUNTIME_CONFIG_FILENAME = "runtime_config.json"


# ============================================================================
# Smoke tests (spec §7 Fase 6)
# ============================================================================
# SmokeError, AI_SMOKE_BODY, BLOCKCHAIN_SMOKE_BODY, tb_post_telemetry,
# tb_get_timeseries, smoke_tests → moved to deploy/onboarding/smoke.py (R5)

# ============================================================================
# Secrets (spec §8)
# ============================================================================
# ENV_TEMPLATE, GATEWAY_ENV_TEMPLATE, render_env, write_atomic, write_secrets
# → moved to deploy/onboarding/secrets.py (R3)


def write_nodered_runtime_config(data_dir: Path, manifest: dict) -> Path:
    """Write runtime config consumed by fn_main from /data/runtime_config.json."""
    runtime_config: dict[str, Any] = {
        "expected_tags": manifest["sensors"]["expected_tags"],
    }
    ai_url = (manifest.get("ai_inference") or {}).get("url")
    if ai_url:
        runtime_config["ai_inference_url"] = ai_url
    target = data_dir / NR_RUNTIME_CONFIG_FILENAME
    payload = json.dumps(runtime_config, ensure_ascii=True, separators=(",", ":")) + "\n"
    write_atomic(target, payload)
    ai_status = "<set>" if ai_url else "<cleared>"
    print(
        f"[✓] NR runtime cfg:  {target} "
        f"(EXPECTED_TAGS={len(runtime_config['expected_tags'])}, AI_INFERENCE_URL={ai_status})"
    )
    return target


# ============================================================================
# NR credentials store (flows_cred.json)
# ============================================================================
#
# Replicates Node-RED's AES-256-CTR encryption for flows_cred.json. Algorithm
# (from @node-red/util/lib/util.js): key = SHA-256(credentialSecret)[:32];
# IV = 16 random bytes; ciphertext = AES-256-CTR(key, IV, JSON.stringify(creds));
# output string = IV.hex() + base64(ciphertext); file = {"$": output_string}.
#
# We write broker_tb.credentials.user as the LITERAL "${TB_GATEWAY_TOKEN}"
# placeholder — NR substitutes it from the process env at runtime.


def nr_encrypt_credentials(secret: str, creds: dict) -> str:
    """Encrypt credentials dict with NR's AES-256-CTR scheme."""
    import base64
    import hashlib
    import json as _json
    import secrets as _secrets
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    key = hashlib.sha256(secret.encode("utf-8")).digest()
    iv = _secrets.token_bytes(16)
    encryptor = Cipher(algorithms.AES(key), modes.CTR(iv), backend=default_backend()).encryptor()
    plaintext = _json.dumps(creds).encode("utf-8")
    ct = encryptor.update(plaintext) + encryptor.finalize()
    return iv.hex() + base64.b64encode(ct).decode("ascii")


def write_nodered_cred_file(data_dir: Path, credential_secret: str) -> Path:
    """Write flows_cred.json with broker_tb.credentials.user = ${TB_GATEWAY_TOKEN}."""
    import json as _json
    creds = {"broker_tb": {"user": "${TB_GATEWAY_TOKEN}", "password": ""}}
    blob = nr_encrypt_credentials(credential_secret, creds)
    target = data_dir / "flows_cred.json"
    target.write_text(_json.dumps({"$": blob}) + "\n")
    print(f"[✓] NR cred file:    {target} (broker_tb.user=${{TB_GATEWAY_TOKEN}} literal)")
    return target


# ============================================================================
# Auto-start helpers (bring-up from-scratch con un solo comando)
#
# El onboarding detecta si TB o NR no están arriba y los levanta vía
# `docker compose up -d <service>` desde la raíz del repo. Idempotente:
# si el servicio ya está arriba, es un no-op. Permite al operador correr
# un único comando: `python3 deploy/onboard_client_v2.py --manifest ...`.
# ============================================================================


def _tb_reachable(url: str, user: str, password: str) -> bool:
    """TB está realmente listo solo cuando `POST /api/auth/login` responde 200
    con body JSON conteniendo un token. La UI de `/login` carga antes, pero
    la REST API de auth puede tardar varios segundos más tras el arranque.
    """
    try:
        r = requests.post(
            f"{url}/api/auth/login",
            json={"username": user, "password": password},
            timeout=3,
        )
        if r.status_code != 200:
            return False
        return "token" in r.text  # no parseamos JSON: basta con un marker barato
    except requests.RequestException:
        return False


def _nr_reachable(url: str) -> bool:
    """NR responde en / (editor) con 200 o 302."""
    try:
        r = requests.get(f"{url}/", timeout=3)
        return r.status_code in (200, 302)
    except requests.RequestException:
        return False


def _compose_up(service: str, extra_env: dict | None = None) -> None:
    """Ejecuta `docker compose up -d <service>` desde la raíz del repo."""
    proc_env = {**os.environ}
    if extra_env:
        proc_env.update(extra_env)
    try:
        subprocess.run(
            ["docker", "compose", "up", "-d", service],
            check=True, capture_output=True, text=True,
            cwd=REPO_ROOT, env=proc_env,
        )
    except subprocess.CalledProcessError as e:
        raise ExternalError(
            f"`docker compose up -d {service}` failed (exit {e.returncode}): "
            f"{e.stderr.strip()[:300]}"
        )
    except FileNotFoundError:
        raise ExternalError(
            "`docker` CLI not found in PATH — install Docker Desktop / docker CLI"
        )


def _wait_until(predicate: Callable[[], bool], timeout: float, label: str, interval: float = 3.0) -> bool:
    """Bloquea hasta que predicate() sea True o se agote timeout."""
    start = time.monotonic()
    last_print = 0.0
    while time.monotonic() - start < timeout:
        if predicate():
            return True
        now = time.monotonic()
        if now - last_print >= 10:  # log cada ~10 s para no spamear
            print(f"[…] waiting for {label} ({int(now - start)}s)...", file=sys.stderr)
            last_print = now
        time.sleep(interval)
    return False


def ensure_tb_up(tb_url: str, user: str, password: str) -> None:
    """Si TB no responde a login, arranca el servicio y espera healthy.
    Primer arranque tarda ~90 s (migraciones Postgres); damos 180 s de colchón.
    El predicado valida no solo que TB esté vivo, sino que su REST API de auth
    responda con un token — evita falsos positivos de la UI que carga antes.
    """
    if _tb_reachable(tb_url, user, password):
        return
    print(f"[…] TB no responde en {tb_url} — arrancando via `docker compose up -d thingsboard`")
    _compose_up("thingsboard")
    if not _wait_until(
        lambda: _tb_reachable(tb_url, user, password),
        timeout=180, label="TB login ready", interval=5,
    ):
        raise ExternalError(f"TB did not become reachable at {tb_url} within 180s")
    print(f"[✓] TB up at {tb_url}")


def ensure_nr_up(nr_url: str, client: str) -> None:
    """Si NR no responde, arranca el servicio y espera healthcheck.

    Pre-requisito: secrets ya escritos (Phase 5 + 5b) — el compose de NR
    los consume via `env_file:`. Se inyecta CLIENT al subprocess para que
    el placeholder `${CLIENT}` del compose se resuelva correctamente.
    """
    if _nr_reachable(nr_url):
        return
    print(f"[…] NR no responde en {nr_url} — arrancando via `docker compose up -d nodered_tb`")
    _compose_up("nodered_tb", extra_env={"CLIENT": client})
    if not _wait_until(lambda: _nr_reachable(nr_url), timeout=60, label="NR ready", interval=3):
        raise ExternalError(f"NR did not become reachable at {nr_url} within 60s")
    print(f"[✓] NR up at {nr_url}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="onboard_client_v2.py",
        description="Provisiona un cliente en el stack v2 (TB profiles + devices + NR config).",
    )
    p.add_argument("--manifest", required=True, help="Ruta al YAML del cliente")
    p.add_argument("--dry-run", action="store_true", help="Valida manifest + pings, no aplica cambios")
    p.add_argument("--force", action="store_true", help="Rota tokens de devices existentes")
    p.add_argument("-v", "--verbose", action="store_true", help="Loggea cada request HTTP")
    p.add_argument(
        "--no-autostart",
        action="store_true",
        help="No auto-lanzar `docker compose up -d` si TB/NR no responden (failfast).",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    # Phase 1: load + validate manifest
    try:
        manifest = load_manifest(Path(args.manifest))
    except (FileNotFoundError, ManifestError) as e:
        print(f"[✗] {e}", file=sys.stderr)
        return EXIT_BAD_INPUT
    # Phase 2a: read env vars
    try:
        env = read_env()
    except RuntimeError as e:
        print(f"[✗] {e}", file=sys.stderr)
        return EXIT_BAD_INPUT
    client = manifest["client"]["id"]
    tags = manifest["sensors"]["expected_tags"]
    print(f"[✓] manifest: {args.manifest} (client={client}, {len(tags)} tags)")
    # --dry-run: validate + ping, no side effects
    if args.dry_run:
        print(f"[dry-run] manifest: {args.manifest} (valid)")
        try:
            jwt = tb_login(env["tb_url"], env["tb_user"], env["tb_password"])
            print(f"[dry-run] TB login: {env['tb_url']} OK")
        except ExternalError as e:
            print(f"[dry-run] {e}", file=sys.stderr)
            return EXIT_EXTERNAL
        if _nr_reachable(env["nr_url"]):
            print(f"[dry-run] NR ping:  {env['nr_url']} OK")
        else:
            print(f"[dry-run] NR unreachable at {env['nr_url']}", file=sys.stderr)
            return EXIT_EXTERNAL
        existing = {p["name"] for p in tb_list_profiles(env["tb_url"], jwt)}
        would_create_profiles = [p for p in REQUIRED_PROFILES if p not in existing]
        would_create_devices = []
        for name in [f"ai-inference-{client}", f"blockchain-anchor-{client}"]:
            if not tb_get_device_by_name(env["tb_url"], jwt, name):
                would_create_devices.append(name)
        print(f"[dry-run] would create: {len(would_create_profiles)} profiles: {would_create_profiles}")
        print(f"[dry-run] would create: {len(would_create_devices)} devices: {would_create_devices}")
        print(
            "[dry-run] would configure NR runtime file: "
            f"{env['nr_data_dir']}/{NR_RUNTIME_CONFIG_FILENAME} ({len(tags)} expected_tags)"
        )
        print(f"[dry-run] would write: deploy/secrets/{client}/*.env")
        print("\nno side effects performed. run without --dry-run to apply.")
        return EXIT_OK
    # Phase 2b: TB login — auto-arranca TB si no está up (salvo --no-autostart).
    if not args.no_autostart:
        try:
            ensure_tb_up(env["tb_url"], env["tb_user"], env["tb_password"])
        except ExternalError as e:
            print(f"[✗] {e}", file=sys.stderr)
            return EXIT_EXTERNAL
    try:
        jwt = tb_login(env["tb_url"], env["tb_user"], env["tb_password"])
    except ExternalError as e:
        print(f"[✗] {e}", file=sys.stderr)
        return EXIT_EXTERNAL
    print(f"[✓] TB login: {env['tb_url']} (user={env['tb_user']})")
    # Phase 3: ensure profiles
    try:
        profile_ids = ensure_profiles(env["tb_url"], jwt)
    except ExternalError as e:
        print(f"[✗] {e}", file=sys.stderr)
        return EXIT_EXTERNAL
    # Phase 4: ensure writeback devices + capture tokens
    try:
        devices = ensure_writeback_devices(env["tb_url"], jwt, client, profile_ids, args.force)
    except ExternalError as e:
        print(f"[✗] {e}", file=sys.stderr)
        return EXIT_EXTERNAL
    # Phase 4b: ensure Gateway device (infra, single-tenant)
    try:
        devices["gateway"] = ensure_gateway_device(env["tb_url"], jwt, profile_ids, args.force)
    except ExternalError as e:
        print(f"[✗] {e}", file=sys.stderr)
        return EXIT_EXTERNAL
    # Phase 5: write secrets — debe ir ANTES de preparar NR. Los `.env` y el
    # flows_cred.json son prerequisitos para que NR pueda arrancar vía
    # `env_file` del compose. En un bring-up from-scratch, NR no existe aún
    # cuando se ejecuta este script por primera vez; el orden garantiza que
    # los artefactos queden escritos incluso si Phase 6 falla.
    secrets_root = Path("deploy/secrets")
    try:
        write_secrets(client, env["tb_url"], devices, secrets_root)
    except OSError as e:
        print(f"[✗] secrets: {e}", file=sys.stderr)
        return EXIT_UNEXPECTED
    # Phase 5b: write NR flows_cred.json (encrypts ${TB_GATEWAY_TOKEN} literal)
    try:
        write_nodered_cred_file(Path(env["nr_data_dir"]), env["nr_credential_secret"])
    except OSError as e:
        print(f"[✗] NR cred file: {e}", file=sys.stderr)
        return EXIT_UNEXPECTED
    # Phase 5c: write runtime config consumed by fn_main.
    try:
        write_nodered_runtime_config(Path(env["nr_data_dir"]), manifest)
    except OSError as e:
        print(f"[✗] NR runtime config: {e}", file=sys.stderr)
        return EXIT_UNEXPECTED
    # Phase 6: ensure NR is reachable. Con --no-autostart, mantenemos modo
    # fail-fast si NR está down para no dar un onboarding falso-positivo.
    if not args.no_autostart:
        try:
            ensure_nr_up(env["nr_url"], client)
        except ExternalError as e:
            print(f"[✗] {e}", file=sys.stderr)
            return EXIT_EXTERNAL
    elif not _nr_reachable(env["nr_url"]):
        print(f"[✗] NR unreachable at {env['nr_url']} (--no-autostart active)", file=sys.stderr)
        return EXIT_EXTERNAL
    # Phase 7: smoke tests
    try:
        smoke_tests(env["tb_url"], jwt, devices)
    except ExternalError as e:
        print(f"[✗] {e}", file=sys.stderr)
        return EXIT_EXTERNAL
    except SmokeError as e:
        print(f"[✗] {e}", file=sys.stderr)
        return EXIT_SMOKE_FAILED
    print(f"\nonboarding complete. servicios ai-advanced y blockchain pueden arrancar "
          f"(env_file apunta a deploy/secrets/{client}/).")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
