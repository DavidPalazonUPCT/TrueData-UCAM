"""Node-RED runtime config + flows_cred.json generation.

- `write_nodered_runtime_config`: writes /data/runtime_config.json (JSON file
  consumed by fn_main). Replaces the older /admin/set-expected-tags route.
- `nr_encrypt_credentials` + `write_nodered_cred_file`: replicates NR's
  AES-256-CTR credential encryption so `flows_cred.json` contains the literal
  `${TB_GATEWAY_TOKEN}` placeholder. NR substitutes it from process env at
  runtime.
"""
import json
from pathlib import Path
from typing import Any

from deploy.onboarding.secrets import write_atomic


NR_RUNTIME_CONFIG_FILENAME = "runtime_config.json"


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
