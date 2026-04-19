"""onboard_client_v2.py — provisioning pipeline v2 para clientes de la plataforma.

Invocar explícitamente con Python 3.9+: `python3 deploy/onboard_client_v2.py ...`
en Linux/macOS o `py deploy\\onboard_client_v2.py ...` en Windows. Sin shebang:
en Windows el `py.exe` launcher podía delegar a un `python3.exe` alias roto de
Microsoft Store y provocar `ModuleNotFoundError` espurios.
"""
import argparse
import os
import sys
from pathlib import Path

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
from deploy.onboarding.nodered import (  # noqa: E402
    NR_RUNTIME_CONFIG_FILENAME,
    write_nodered_runtime_config, write_nodered_cred_file,
)
from deploy.onboarding.docker_helpers import (  # noqa: E402
    _nr_reachable, ensure_tb_up, ensure_nr_up,
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
# NR_RUNTIME_CONFIG_FILENAME, write_nodered_runtime_config, nr_encrypt_credentials,
# write_nodered_cred_file → moved to deploy/onboarding/nodered.py (R6)

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


# ============================================================================
# Auto-start helpers → moved to deploy/onboarding/docker_helpers.py (R7)
# ============================================================================


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
