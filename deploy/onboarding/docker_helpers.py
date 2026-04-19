"""Docker compose auto-start helpers.

`ensure_tb_up` and `ensure_nr_up` are idempotent: if the service responds,
no-op; otherwise `docker compose up -d <svc>` and wait for readiness.
"""
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

import requests

from deploy.onboarding.tb import ExternalError, HTTP_TIMEOUT  # noqa: F401


# Repo root — three levels above this file:
# deploy/onboarding/docker_helpers.py → deploy/onboarding/ → deploy/ → repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


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
