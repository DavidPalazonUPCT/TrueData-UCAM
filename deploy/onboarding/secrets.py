"""Secrets rendering + atomic writes (spec §8).

Writes `.env` files consumable by downstream services via Docker `env_file:`.
No POSIX-mode enforcement — protection is operator responsibility. See
deploy/README.md "Protección de deploy/secrets/".
"""
from datetime import datetime, timezone
from pathlib import Path


ENV_TEMPLATE = """\
# onboard_client_v2.py — generated {timestamp}
# DO NOT EDIT MANUALLY. Regenerate via deploy/onboard_client_v2.py.
# Deliver this file to the {service_team} team via secure channel.
CLIENT={client}
TB_HOST={tb_host}
TB_DEVICE_NAME={device_name}
TB_DEVICE_TOKEN={token}
"""

GATEWAY_ENV_TEMPLATE = """\
# onboard_client_v2.py — generated {timestamp}
# DO NOT EDIT MANUALLY. Regenerate via deploy/onboard_client_v2.py.
# Consumed by truedata-nodered/docker-compose.yml via env_file directive.
# Node-RED substitutes ${{TB_GATEWAY_TOKEN}} in mqtt-broker.credentials.user at runtime.
TB_GATEWAY_TOKEN={token}
"""


def render_env(client: str, tb_host: str, device_name: str, token: str, service_team: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return ENV_TEMPLATE.format(
        timestamp=now,
        service_team=service_team,
        client=client,
        tb_host=tb_host,
        device_name=device_name,
        token=token,
    )


def write_atomic(path: Path, content: str) -> None:
    """Write file atomically, portably. No POSIX-mode enforcement.

    File-system-level protection is the operator's responsibility (OS user
    perms on deploy/secrets/, disk encryption, etc.). See deploy/README.md.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    tmp.replace(path)


def write_secrets(client: str, tb_host: str, devices: dict, secrets_root: Path) -> list[Path]:
    client_dir = secrets_root / client
    client_dir.mkdir(parents=True, exist_ok=True)
    specs = [
        ("ai",         "ai-inference.env",      "AI service"),
        ("blockchain", "blockchain-anchor.env", "blockchain service"),
    ]
    written = []
    for role, filename, team in specs:
        content = render_env(
            client=client,
            tb_host=tb_host,
            device_name=devices[role]["name"],
            token=devices[role]["token"],
            service_team=team,
        )
        target = client_dir / filename
        write_atomic(target, content)
        written.append(target)
        print(f"[✓] secrets written: {target}")
    # Gateway env — consumed by NR docker-compose env_file
    gw_content = GATEWAY_ENV_TEMPLATE.format(
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        token=devices["gateway"]["token"],
    )
    gw_target = client_dir / "nodered-gateway.env"
    write_atomic(gw_target, gw_content)
    written.append(gw_target)
    print(f"[✓] secrets written: {gw_target}")
    return written
