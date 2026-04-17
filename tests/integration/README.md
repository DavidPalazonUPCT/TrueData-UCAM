# Integration tests — pipeline v2

Suite de regresión contra la implementación v2 (NR + TB + mock ML).

## Prerrequisitos

1. Stack Docker arriba:
   ```bash
   docker compose up -d
   ```
2. Red externa:
   ```bash
   docker network create truedata_iot_network  # si no existe
   ```
3. NR con `NR_ADMIN_ENABLED=true` y `extra_hosts: host.docker.internal:host-gateway`
   (ya configurado en `truedata-nodered/docker-compose.yml`).
4. Dependencias de test:
   ```bash
   pip install -r requirements-dev.txt
   ```
5. Credenciales TB:
   ```bash
   export TB_USER=tenant@thingsboard.org
   export TB_PASS=tenant
   ```

## Ejecutar

```bash
pytest tests/integration/ -v
```

## Qué valida

- **Bloque A** (9): validación defensiva del endpoint (`/api/opc-ingest`).
- **Bloque B** (4): comportamiento con valores null, tipos cambiantes, extremos, idempotencia.
- **Bloque C** (2): tags fuera de EXPECTED_TAGS, dropout LOCF.
- **Bloque Warmup** (2): gate LOCF pre/post warmup.
- **Bloque F** (5): escenarios OPC-UA realistas (out-of-order, reconnect, fragmentation, ts window, fault+recovery).

Total: **22 tests** + runbook manual F1 (multi-rate burst) en `docs/testing/runbooks/`.

## Troubleshooting

- **Mock ML no recibe nada**: verificar que NR alcanza `host.docker.internal`:
  ```bash
  docker exec <container_nr> curl -s http://host.docker.internal:<puerto>/
  ```
- **TB auth falla**: el token expira a las 2h; re-lanzar `pytest` lo re-autentica (fixture session-scoped fresca).
- **Tests flaky por timing**: aumentar `wait_for_ml` timeout vía env var si fuera necesario (no implementado; fixar si aparece).
