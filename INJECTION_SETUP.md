# Guía: Puesta en Marcha del Inyector de Datos (DEMO)

Este documento describe el flujo para inyectar datos históricos contra una
instancia de ThingsBoard usando `simulator/simulador_sensores.py`.

---

## Contexto

El inyector envía datos históricos al endpoint de telemetría de ThingsBoard
**sensor a sensor**. Para ello necesita el `accessToken` específico de cada
dispositivo registrado en la instancia destino.

El destino se configura mediante la variable de entorno `ROOT`. Por defecto
apunta a `http://localhost:9090` (TB local). Para apuntar a una instancia
remota, exporta `ROOT=http://<host>:9090` antes de lanzar.

---

## Pasos

### 1. Verificar conectividad con la instancia ThingsBoard

```bash
ROOT="${ROOT:-http://localhost:9090}"
curl -X POST "${ROOT}/api/v1/<DEVICE_TOKEN>/telemetry" \
  -H "Content-Type: application/json" \
  -d '{"POT_CCM": 55.3}'
```

Esperado: `200 OK`. Reemplaza `<DEVICE_TOKEN>` por el `accessToken` de un
dispositivo provisionado vía la pipeline `deploy/`.

---

### 2. Generar/regenerar los tokens (`fetch_tokens_remote.py`)

```bash
ROOT="${ROOT:-http://localhost:9090}" python3 fetch_tokens_remote.py
```

Este script:
1. Hace login en la instancia ThingsBoard apuntada por `ROOT`.
2. Consulta el ID y `accessToken` de cada sensor configurado para el cliente
   (variable `CLIENT`, por defecto `ESAMUR`).
3. Genera el fichero `deploy/<CLIENT>/DeviceimportCredentials_<CLIENT>.csv`
   con los tokens.

> [!NOTE]
> El directorio `deploy/<CLIENT>/` no se versiona en este repo (los tokens
> son sensibles). Se crea localmente al ejecutar la pipeline de despliegue
> o el `fetch_tokens_remote.py`.

---

### 3. Lanzar el simulador

```bash
ROOT="${ROOT:-http://localhost:9090}" python3 simulator/simulador_sensores.py --client ESAMUR
```

El simulador lee los tokens del CSV generado en el paso 2 y emite POST
`/api/v1/{token}/telemetry` por cada fila del dataset.

**Verificación:** abre la UI de ThingsBoard en `${ROOT}` → *Device Groups* →
*All* → elige un sensor → *Latest Telemetry*. Los valores deben actualizarse
según el dataset.

---

## Resumen de comandos (en orden)

```bash
# Localmente (TB en 9090)
python3 fetch_tokens_remote.py
python3 simulator/simulador_sensores.py --client ESAMUR

# Contra TB remoto
export ROOT=http://<TB_HOST>:9090
python3 fetch_tokens_remote.py
python3 simulator/simulador_sensores.py --client ESAMUR

# Opcional: limitar filas o ajustar velocidad
python3 simulator/simulador_sensores.py --client ESAMUR --delay 0.5 --limit 100
```

> [!IMPORTANT]
> Los tokens son propios de cada instancia de ThingsBoard. Si la URL de
> destino cambia (o se reinicia TB con DB limpia), vuelve a ejecutar
> `fetch_tokens_remote.py` antes de lanzar el simulador.
