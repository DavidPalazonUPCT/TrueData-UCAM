# Contrato: entrega de secrets de `base/` a los servicios externos

Contrato operacional entre el módulo **`base/`** (plataforma — operado por
UCAM) y los servicios externos del monorepo (**ai-advanced**,
**blockchain**) sobre **cómo se entregan**, **consumen** y **rotan** los
access tokens de ThingsBoard que cada servicio necesita para escribir
telemetría.

Complementa a:
- [`ai-service.md`](ai-service.md) §A6 — política de rotación del token AI
- [`blockchain-writeback.md`](blockchain-writeback.md) §A6 — política de rotación del token blockchain

Este doc formaliza el **mecanismo de entrega**; los dos anteriores
formalizan el **uso** del token ya entregado.

---

## 1. Resumen

`python3 -m deploy.onboarding` (lógica en `base/deploy/onboarding/`)
provisiona todos los recursos en TB y emite **ficheros `.env`** con los
tokens, uno por servicio consumidor. Los servicios externos los leen vía
la directiva `env_file:` de Docker compose — cero glue code, cero
llamadas HTTP out-of-band.

**Invariantes que la plataforma garantiza:**
- Escritura atómica (tmp + rename). Nunca vas a leer un fichero a medias.
- Shape estable (mismas 4 claves siempre; ver §3).
- Re-ejecución idempotente: si el token no cambia, el valor tampoco
  (solo cambia el timestamp del header).
- Rotación atómica con `--force`: token nuevo y viejo invalidado en el
  mismo momento.

---

## 2. Ficheros producidos — quién consume cada uno

Ruta canónica: `base/deploy/secrets/<CLIENT>/<file>.env` (gitignored).

| Fichero | Escrito por | Consumido por | ¿Qué contiene? |
|---|---|---|---|
| `ai-inference.env` | `base/` onboarding | **ai-advanced** | Credenciales del device `ai-inference-<CLIENT>` |
| `blockchain-anchor.env` | `base/` onboarding | **blockchain** | Credenciales del device `blockchain-anchor-<CLIENT>` |
| `nodered-gateway.env` | `base/` onboarding | **`base/` NR** (interno) | ⛔ **NO CONSUMIR** — uso interno del módulo base |

**Regla de oro:** si el nombre del fichero no coincide con el rol de tu
servicio, no lo toques.

También se genera (fuera de `deploy/secrets/`):
- `base/truedata-nodered/data/flows_cred.json` — credenciales cifradas
  de Node-RED. ⛔ **Archivo interno de `base/`**, no es consumible.

---

## 3. Shape del `.env` (contrato estable)

Todos los ficheros de `deploy/secrets/<CLIENT>/` (excepto
`nodered-gateway.env`, que es interno) exponen exactamente estas 4 env
vars:

```env
# deploy.onboarding — generated 2026-04-20T08:39:22Z
# DO NOT EDIT MANUALLY. Regenerate via `python3 -m deploy.onboarding --manifest <path>`.
# Deliver this file to the AI service team via secure channel.
CLIENT=FR_ARAGON
TB_HOST=http://thingsboard:9090
TB_DEVICE_NAME=ai-inference-FR_ARAGON
TB_DEVICE_TOKEN=<20 chars alfanuméricos>
```

| Key | Uso esperado en el servicio consumidor |
|---|---|
| `CLIENT` | Tag para métricas, logs y headers (identifica la planta) |
| `TB_HOST` | URL base de TB. Compón la URL de writeback como `${TB_HOST}/api/v1/${TB_DEVICE_TOKEN}/telemetry` |
| `TB_DEVICE_NAME` | Solo debugging bilateral con la plataforma (ej. aparece en los logs de TB) |
| `TB_DEVICE_TOKEN` | ⚠️ **Credencial**. Viaja en el path de la URL (limitación TB CE, no header). Único campo sensible |

> **Sobre `TB_HOST`**: el valor escrito al `.env` proviene del env var
> `TB_URL` del onboarding (default `http://localhost:9090`). El operador
> debe exportar `TB_URL=http://thingsboard:9090` antes de `python3 -m
> deploy.onboarding` cuando los servicios consumidores corran
> containerizados en la red `truedata-net` (caso típico en producción y
> en el monorepo gitlab). Si el servicio corre en el host para dev,
> dejar el default. Ver §4.3.

**Este contrato es estable.** Si en el futuro se añade una 5ª key (p. ej.
`TB_DEVICE_ID`), será **additive** — no se van a renombrar ni quitar las
4 existentes sin un major-version bump documentado.

---

## 4. Cómo se consume (Docker compose)

La forma canónica es la directiva `env_file:` del compose del servicio
externo. Docker inyecta los `KEY=value` como env vars del contenedor en
`container-create`, sin manipular el sistema de ficheros.

### 4.1 Ejemplo mínimo — ai-advanced

En `ai-advanced/docker-compose.yml` (monorepo: `ai-advanced/` y `base/`
son hermanos):

```yaml
services:
  ai-advanced:
    image: truedata/ai-advanced:latest
    env_file:
      - ../base/deploy/secrets/${CLIENT:?CLIENT must be set (export CLIENT=<id> or add to .env)}/ai-inference.env
    networks:
      - truedata-net

networks:
  truedata-net:
    external: true
```

El `${CLIENT:?...}` hace que `docker compose` **falle rápido y claro**
si `CLIENT` no está en el entorno — sin mensajes crípticos de
`env_file not found`.

### 4.2 Ejemplo paralelo — blockchain

```yaml
services:
  blockchain:
    image: truedata/blockchain:latest
    env_file:
      - ../base/deploy/secrets/${CLIENT:?CLIENT must be set}/blockchain-anchor.env
    networks:
      - truedata-net
```

### 4.3 Red y DNS

Todos los servicios del monorepo (`base`, `ai-advanced`, `blockchain`)
deben estar en la red `truedata-net`. En esa red, TB es accesible por DNS
interno como `thingsboard:9090`.

`TB_HOST` en el `.env` apuntará a `http://thingsboard:9090` cuando los
servicios corran containerizados en la misma red. En entornos de
desarrollo donde el servicio externo corre en el host, puede sobreescribirse
a `http://localhost:9090`.

---

## 5. Orden de arranque

**Single-tenant, dependency-driven:**

```
1. base/ onboarding corre primero
   $ python3 -m deploy.onboarding --manifest deploy/clients/<CLIENT>.yaml
   → provisiona TB, configura NR, escribe los 3 .env

2. base/ NR ya está corriendo (auto-arrancado en paso 1)

3. Servicios externos arrancan DESPUÉS
   $ docker compose up -d ai-advanced blockchain
   → env_file resuelve correctamente (los .env ya existen)
```

El compose global del monorepo debería encadenar estos pasos con
`depends_on:` y healthchecks (ver `docker-compose.example.yml` en la raíz
de este repo).

---

## 6. Rotación de tokens

Gobernada por `--force` en el onboarding:

```bash
python3 -m deploy.onboarding --manifest deploy/clients/<CLIENT>.yaml --force
```

Al ejecutarse:
1. TB rota los tokens atómicamente (viejos → inválidos, nuevos emitidos)
2. `base/` reescribe los 3 `.env` con el nuevo valor de `TB_DEVICE_TOKEN`
3. `base/` regenera `flows_cred.json` + reinicia NR (auto)

**Acción requerida por el servicio consumidor:**

Docker inyecta el `env_file:` en **container-create time**. Si tu
contenedor ya está corriendo, **sigue con el token viejo en memoria** —
empezarás a ver `401` al siguiente writeback. Para recoger el nuevo:

```bash
docker compose restart ai-advanced     # o
docker compose up -d --force-recreate ai-advanced
```

El downtime es del orden de segundos. Notificación out-of-band (ver
§A6 de `ai-service.md` / `blockchain-writeback.md`) llega con ≥24 h
de antelación salvo compromiso confirmado.

---

## 7. Verificación unilateral (smoke test del dev externo)

Antes de arrancar tu servicio por primera vez:

```bash
# 1. ¿Existe el fichero que mi servicio va a consumir?
test -f ../base/deploy/secrets/${CLIENT}/ai-inference.env && echo "OK file" || echo "FAIL: onboarding no ha corrido"

# 2. ¿Tiene las 4 keys esperadas?
grep -Eq '^(CLIENT|TB_HOST|TB_DEVICE_NAME|TB_DEVICE_TOKEN)=' \
    ../base/deploy/secrets/${CLIENT}/ai-inference.env && echo "OK shape"

# 3. ¿El token vale? Manda un POST de prueba
source ../base/deploy/secrets/${CLIENT}/ai-inference.env
curl -s -o /dev/null -w "smoke=%{http_code}\n" \
    -X POST "${TB_HOST}/api/v1/${TB_DEVICE_TOKEN}/telemetry" \
    -H "Content-Type: application/json" \
    -d '{"ts":'$(date +%s%3N)',"values":{"smoke":1}}'
# Expected: smoke=200
```

---

## 8. Qué NO hacer

- ❌ **No editar** los ficheros `.env` manualmente. La próxima ejecución
  de `base/` los sobreescribe sin aviso.
- ❌ **No consultar** `nodered-gateway.env` ni `flows_cred.json`. Son
  internos de `base/` y pueden cambiar sin notificación.
- ❌ **No hardcodear** el token en tu código, config, image o
  `docker-compose.yml`. Siempre via `env_file:`.
- ❌ **No commitear** estos ficheros a ningún repo — están gitignored en
  `base/` por diseño. Si apareciesen en tu repo, es un incident de
  seguridad (token comprometido).
- ❌ **No asumir** que el fichero siempre está ahí. Si tu servicio
  arranca antes que el onboarding, `env_file` fallará. Usa
  `depends_on:` / `condition: service_started`.
- ❌ **No implementar** tu propio fetching de tokens (no hay API HTTP de
  secrets en este MVP). Si necesitas rotación programática, pide un spec
  nuevo.

---

## 9. Troubleshooting

| Síntoma | Causa probable | Fix |
|---|---|---|
| `docker compose up` → `env file not found` | `CLIENT` env var no está set, o el onboarding no ha corrido aún | `export CLIENT=<id>` + correr `base/` onboarding primero |
| `docker compose up` → `required variable CLIENT is missing a value` | Idem (el `${CLIENT:?...}` hizo su trabajo) | Igual que arriba |
| Writebacks devuelven `401` | Token rotado, tu container sigue con el viejo en memoria | `docker compose restart <tu-servicio>` |
| Writebacks devuelven `200` pero los datos no aparecen en TB | No es problema de secrets; probablemente rule chain del profile — contactar plataforma | — |
| Quiero probar sin que `base/` corra onboarding | No es un flujo soportado. Si es para CI unit-testing aislado, usa fixtures en tu propio repo con tokens fake | — |

---

## 10. Historial

| Fecha | Cambio |
|---|---|
| 2026-04-20 | Primera versión — formaliza el mecanismo de entrega que hasta ahora vivía implícito en `deploy/README.md` y §A6 de los contratos de writeback |
