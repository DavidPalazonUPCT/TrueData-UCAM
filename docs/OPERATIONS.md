# Runbook operacional — TRUEDATA base/

Para operadores (SRE, DevOps) que despliegan el stack en un host y
responden a pages. **No** es tutorial para devs; para eso ver
`docs/SETUP.md` y `deploy/README.md`.

**Índice:**

1. [Pre-flight](#1-pre-flight)
2. [Bring-up canónico](#2-bring-up-canónico)
3. [Healthcheck sequence](#3-healthcheck-sequence)
4. [Rotación de tokens](#4-rotación-de-tokens)
5. [Cambiar configuración runtime de NR sin re-onboardear](#5-cambiar-configuración-runtime-de-nr)
6. [Backup + restore](#6-backup--restore)
7. [Disaster recovery](#7-disaster-recovery)
8. [Logs](#8-logs)
9. [Troubleshooting](#9-troubleshooting)
10. [Regenerar password del editor NR](#10-regenerar-password-del-editor-nr)

---

## 1. Pre-flight

Requisitos del host:

- Docker Engine 24+ y Compose v2.20+
- Python 3.9+
- Red: puertos `1880` (NR UI), `9090` (TB HTTP), `1883` (TB MQTT), `5432`
  (Postgres) libres en el host

```bash
pip install -r requirements.txt
cp .env.example .env
```

Editar `.env`:

```ini
CLIENT=FR_ARAGON                 # required — cliente target
TB_ADMIN_PASSWORD=tenant         # required — default es 'tenant' en dev
TB_URL=http://thingsboard:9090   # opcional — setear si servicios externos corren containerizados
```

Solo `CLIENT` y `TB_ADMIN_PASSWORD` son obligatorios. Ver `.env.example`
para el resto.

---

## 2. Bring-up canónico

Stack desde cero en un solo comando:

```bash
python3 -m deploy.onboarding --manifest deploy/clients/${CLIENT}.yaml
```

**Duración esperada:**
- Primera ejecución: **3-5 min** (migración inicial de Postgres en TB)
- Re-ejecuciones: **5-10 s** (idempotente, todo ya provisionado)

**Qué hace (en orden):**

1. Valida manifest + env vars
2. `docker compose up -d thingsboard` si TB no responde, espera ≤180 s
3. Asegura 5 profiles + 3 devices en TB (idempotente)
4. Escribe `deploy/secrets/${CLIENT}/*.env` (3 ficheros)
5. Escribe `truedata-nodered/data/flows_cred.json` (AES-256-CTR)
6. Escribe `truedata-nodered/data/runtime_config.json`
7. `docker compose up -d nodered_tb` si NR no responde, espera ≤60 s
8. Smoke tests contra los writeback devices
9. Exit 0 + mensaje "onboarding complete"

**Servicios externos (ai-advanced, blockchain)** arrancan DESPUÉS del
onboarding, cuando los `.env` ya existen:

```bash
docker compose -f docker-compose.example.yml up -d ai-advanced blockchain
```

Ver `docs/contracts/secrets-delivery.md` §5 para detalles del orden.

---

## 3. Healthcheck sequence

Orden de checks, de superficial a profundo:

### 3.1 Containers up

```bash
docker compose ps
# Esperado: 3 containers (thingsboard, nodered_tb, postgres-db), todos Up
# "healthy" tras ~90s (TB) y ~30s (NR)
```

### 3.2 HTTP responde

```bash
# TB UI
curl -sI http://localhost:9090/login | head -1
# Esperado: HTTP/1.1 200 OK

# NR UI
curl -sI http://localhost:1880/ | head -1
# Esperado: HTTP/1.1 200 OK
```

### 3.3 TB API funcional (no solo UI)

```bash
JWT=$(curl -s -X POST http://localhost:9090/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"tenant@thingsboard.org","password":"'$TB_ADMIN_PASSWORD'"}' \
  | jq -r .token)
[ -n "$JWT" ] && [ "$JWT" != "null" ] && echo "TB API OK" || echo "TB API DOWN"
```

### 3.4 NR pipeline funcional

```bash
curl -s -X POST http://localhost:1880/api/opc-ingest \
  -H "Content-Type: application/json" \
  -d "{\"ts\": $(date +%s%3N), \"values\": {\"HEALTHCHECK\": 1}}"
# Esperado: {"status":"ok","tags":1,"inference":"..."}
# Cualquier 200 = pipeline alive. 4xx = NR up pero mal configurado.
```

### 3.5 MQTT NR → TB (el path real de datos)

```bash
# Verificar que NR ha inyectado TB_GATEWAY_TOKEN
docker exec truedata-nodered_tb-1 printenv TB_GATEWAY_TOKEN | head -c 4 && echo "... (token set)"

# Logs de NR: buscar el "Connected to broker" reciente
docker logs truedata-nodered_tb-1 --tail 50 2>&1 | grep -E "mqtt|MQTT"
# Esperado: "Connected to broker: nodered-gateway-... @mqtt://thingsboard:1883"
```

### 3.6 Invariantes estructurales (automatizadas)

```bash
pytest tests/integration/test_bringup_v2.py -v
# 4 tests: profiles, Gateway flag, writeback device profile bindings
```

### 3.7 End-to-end (con datos reales)

```bash
pytest tests/integration/ -v
# 30 tests — cubre ingesta, LOCF, AI path, rule chains
```

Ver `docs/testing/pre-production.md` para escenarios con el simulator y
dump real FR_ARAGON.

---

## 4. Rotación de tokens

Mecanismo completo (incluyendo contrato con servicios externos) en
`docs/contracts/secrets-delivery.md` §6. Resumen operacional:

### 4.1 Rotar los 3 tokens de device (AI, blockchain, Gateway NR)

```bash
python3 -m deploy.onboarding --manifest deploy/clients/${CLIENT}.yaml --force
```

Qué pasa automáticamente:
- TB invalida los 3 tokens viejos atómicamente
- Se reescriben los 3 `deploy/secrets/${CLIENT}/*.env` con los nuevos
- Se regenera `flows_cred.json`
- NR se reinicia solo para pickup el nuevo Gateway token

### 4.2 Servicios externos tienen que reiniciar

Docker inyecta `env_file:` en container-create time. Los servicios
externos que ya corrían tienen el token viejo en memoria → empezarán a
ver `401` al siguiente writeback. **Tras cualquier `--force` del
onboarding, reiniciar:**

```bash
docker compose restart ai-advanced blockchain
# O si usas docker-compose.example.yml:
docker compose -f docker-compose.example.yml restart ai-advanced blockchain
```

Downtime ~segundos. Notificación previa al equipo externo: ver §A6 de
`ai-service.md` / `blockchain-writeback.md` (≥24 h salvo compromiso
confirmado).

### 4.3 Rotar la password admin de TB

No automatizado. Vía TB UI como `sysadmin@thingsboard.org` /
`sysadmin`, después actualizar `TB_ADMIN_PASSWORD` en el `.env` raíz.

### 4.4 Rotar la password del editor NR

Ver §10 abajo.

---

## 5. Cambiar configuración runtime de NR

El function node `fn_main` lee `truedata-nodered/data/runtime_config.json`
en cada scan. Cambios a este fichero **se aplican en la siguiente
ingesta** sin restart de NR. Dos usos típicos:

### 5.1 Cambiar la URL del servicio AI (o silenciarlo)

```bash
# Ver config actual
cat truedata-nodered/data/runtime_config.json | jq

# Set URL AI (salida 2 activa)
python3 - <<'PY'
import json
from pathlib import Path
p = Path("truedata-nodered/data/runtime_config.json")
cfg = json.loads(p.read_text()) if p.exists() else {}
cfg["ai_inference_url"] = "http://ai-advanced:5000/api/inference"
p.write_text(json.dumps(cfg, separators=(",", ":")) + "\n")
PY

# Silenciar AI (borrar la clave)
python3 - <<'PY'
import json
from pathlib import Path
p = Path("truedata-nodered/data/runtime_config.json")
cfg = json.loads(p.read_text())
cfg.pop("ai_inference_url", None)
p.write_text(json.dumps(cfg, separators=(",", ":")) + "\n")
PY
```

### 5.2 Cambiar la lista de `expected_tags` (warm-up gate LOCF)

Editar el manifest (`deploy/clients/${CLIENT}.yaml`) + re-ejecutar
onboarding. El warm-up se reinicia automáticamente (cache en memoria
de NR se vacía al restart implícito tras reescritura de
`runtime_config.json` — el flow recarga en siguiente scan).

---

## 6. Backup + restore

### 6.1 Qué se persiste

| Ubicación | Contenido | Cómo se persiste |
|---|---|---|
| Volumen Docker `truedata_postgres-data` | Todas las tablas de TB (devices, telemetría, rule chains, configuración) | Volumen nombrado de Docker |
| Volumen Docker `truedata_tb-data` | Datos de aplicación de TB (caché, temporales) | Volumen nombrado de Docker |
| `truedata-nodered/data/` | Flow (`flows.json`), runtime config (`runtime_config.json`), credenciales cifradas (`flows_cred.json`) | Bind mount desde el host |
| `deploy/secrets/${CLIENT}/` | `.env` con tokens device | Gitignored, regenerable por onboarding |

### 6.2 Backup

```bash
BACKUP_DIR=/var/backups/truedata/$(date +%Y%m%d-%H%M%S)
sudo mkdir -p "$BACKUP_DIR"

# 1. Parar el stack (Postgres no se respalda en caliente de forma segura)
docker compose down

# 2. Volúmenes TB (Postgres + app data)
sudo tar czf "$BACKUP_DIR/tb-volumes.tar.gz" \
  -C /var/lib/docker/volumes \
  truedata_postgres-data truedata_tb-data

# 3. Flows NR (bind mount, incluye runtime_config.json pero NO flows_cred.json)
sudo tar czf "$BACKUP_DIR/nodered-data.tar.gz" \
  --exclude='flows_cred.json' \
  truedata-nodered/data

# 4. Manifests (importante: son la fuente de verdad para re-onboardear)
sudo tar czf "$BACKUP_DIR/clients.tar.gz" deploy/clients

# 5. Restart
docker compose up -d
```

El fichero `flows_cred.json` NO se incluye — lo regenera el onboarding.
Los `deploy/secrets/${CLIENT}/*.env` tampoco — idem.

### 6.3 Restore

```bash
BACKUP_DIR=/var/backups/truedata/<timestamp>

# 1. Parar el stack
docker compose down

# 2. Restaurar volúmenes TB
sudo tar xzf "$BACKUP_DIR/tb-volumes.tar.gz" -C /var/lib/docker/volumes

# 3. Restaurar flows NR
sudo tar xzf "$BACKUP_DIR/nodered-data.tar.gz"

# 4. Restaurar manifests
sudo tar xzf "$BACKUP_DIR/clients.tar.gz"

# 5. Arrancar + re-ejecutar onboarding (regenera secrets + flows_cred.json)
docker compose up -d thingsboard
python3 -m deploy.onboarding --manifest deploy/clients/${CLIENT}.yaml
# Se verá [=] en todos los profiles/devices (ya existen post-restore)
```

### 6.4 Sin drill de restore, el backup no es un backup

Probar el procedimiento al menos una vez en un host de staging antes de
depender de él. Restore de un Postgres de TB es lento (recrea índices):
10-30 min en un snapshot de 1 GB.

---

## 7. Disaster recovery

### 7.1 NR crashea (SPOF de ingesta)

```bash
docker compose restart nodered_tb
# Flows y configs están bind-mounted desde disco — no data loss

# Si el restart falla (p.ej. flows_cred.json corrupto):
python3 -m deploy.onboarding --manifest deploy/clients/${CLIENT}.yaml
# Regenera flows_cred.json idempotentemente
```

**OPC Client durante downtime de NR**: comportamiento no verificado.
Neoradix (vendor externo) puede o no implementar store-and-forward
persistente. Ver [`opc-ingest.md §A4`](contracts/opc-ingest.md) para el
gap operacional reconocido y el plan de test/mitigación. Mayor riesgo de
data loss del sistema en producción continua; aceptable para la demo
INCIBE con ventana acotada.

### 7.2 TB crashea

```bash
docker compose restart thingsboard

# Si Postgres es el problema
docker logs postgres-db
docker compose restart db thingsboard

# Si hay error de permisos en los volúmenes
sudo chmod -R 777 truedata-thingsboard/tb-data
sudo chmod 750 truedata-thingsboard/tb-data/db
docker compose restart thingsboard
```

### 7.3 Restart completo del stack

```bash
docker compose down && docker compose up -d
# TB ~90 s. NR ~30 s. Primera arranque con volumen vacío: 3-5 min.
```

### 7.4 Pérdida total del host

Sin backup externo: telemetría histórica se pierde. Re-deploy:

```bash
git clone <repo>
cd TrueData-UCAM
cp .env.example .env && editar
docker compose up -d thingsboard
python3 -m deploy.onboarding --manifest deploy/clients/${CLIENT}.yaml
# NR se auto-arranca. OPC Client resumirá ingesta cuando la red responda.
```

---

## 8. Logs

```bash
# TB en vivo
docker compose logs -f thingsboard

# Postgres (si TB no arranca)
docker logs -f postgres-db

# NR en vivo
docker compose logs -f nodered_tb

# Errores recientes de MQTT/auth en NR
docker compose logs --tail=200 nodered_tb | grep -iE 'mqtt|auth|error'

# Logs persistidos de TB (post-mortem)
docker exec -it truedata-thingsboard-1 ls /var/log/thingsboard
```

---

## 9. Troubleshooting

| Síntoma | Causa probable | Acción |
|---|---|---|
| `docker compose up` falla con `required variable CLIENT is missing` | `CLIENT` no exportado y no está en `.env` | `export CLIENT=<id>` o añadir al `.env` raíz |
| TB no arranca | Postgres no ready. Volumen corrupto | `docker logs postgres-db`. Esperar 90 s en primer arranque. Si persiste → §7.2 |
| `docker compose ps` muestra TB `unhealthy` pero HTTP responde | Healthcheck pide `/login` pero TB está migrando la DB | Esperar a que termine (≤5 min primera vez) |
| `POST /api/opc-ingest` devuelve `400 ts outside acceptable window` | `ts` fuera de `[now-30d, now+5min]` — típico replayando dumps viejos | Usar `simulator/opc_client_v2.py --shift-to-now` |
| `POST /api/opc-ingest` devuelve `400 body not valid JSON object` | Body ausente o no-JSON | Verificar `Content-Type: application/json` y body no vacío |
| Devices no aparecen en TB tras POST válido | `TB_GATEWAY_TOKEN` no inyectado o broker desconectado | `docker exec truedata-nodered_tb-1 printenv TB_GATEWAY_TOKEN`; `docker compose logs nodered_tb \| grep mqtt` |
| `flows_cred.json` corrupto o borrado | Edit manual o filesystem error | `python3 -m deploy.onboarding --manifest deploy/clients/${CLIENT}.yaml` lo regenera |
| Salida AI silenciada permanentemente | `runtime_config.json` sin `ai_inference_url` | Ver §5.1 |
| Servicio externo devuelve `401` al postear a TB | Token rotado, container no recogió nuevo env | `docker compose restart ai-advanced` (o `blockchain`) |
| Device auto-provisionado sin rule chain | Profile `sensor_planta` no existía cuando llegó primer `connect` | Re-ejecutar onboarding + `docker compose restart nodered_tb` |
| Error permisos en `tb-data/` | Volumen Docker con dueño incorrecto | `sudo chmod -R 777 tb-data && sudo chmod 750 tb-data/db` |
| Login UI TB falla | Password admin rotada fuera del pipeline | Recuperar via SQL en Postgres, o recrear volumen |
| Cambios en `settings.js` no aplican | El archivo se monta como volumen | `docker compose restart nodered_tb` |

---

## 10. Regenerar password del editor NR

```bash
node -e "console.log(require('bcryptjs').hashSync('tu_password', 8))"
# Pegar el hash en truedata-nodered/settings.js → adminAuth.users[0].password
docker compose restart nodered_tb
```

---

## Limitaciones conocidas (MVP)

- **Alerting**: no hay Prometheus ni endpoint estructurado de health por
  servicio. En producción real, wrap un exporter externo o monitor de
  logs con `docker logs --tail`. No bloqueante para la demo regulatoria.
- **Store-and-forward del OPC Client (Neoradix)**: no verificado
  empíricamente. Plan de test + mitigación en
  [`opc-ingest.md §A4`](contracts/opc-ingest.md). Mayor riesgo de data
  loss en producción continua. Aceptable para la demo con ventana
  acotada.
