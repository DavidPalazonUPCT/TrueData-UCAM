# Guía: Puesta en Marcha del Inyector de Datos ESAMUR

Este documento resume los pasos exactos que se siguieron para conseguir que el simulador de inyección de datos funcione correctamente contra el servidor ThingsBoard remoto.

---

## Contexto

El inyector (`simulador_sensores.py`) envía datos históricos de ESAMUR al endpoint de telemetría de ThingsBoard **sensor a sensor**. Para ello necesita el `accessToken` específico de cada dispositivo registrado en la instancia de ThingsBoard destino.

**Servidor ThingsBoard activo**: `http://18.185.1.118:9090`

---

## Pasos Realizados

### 1. Verificar conectividad con la máquina remota

Se lanzó un `curl` de prueba para comprobar que el servidor era accesible:

```bash
curl -X POST "http://18.185.1.118:9090/api/v1/N61v3NqeplzKyUaR3jsC/telemetry" \
  -H "Content-Type: application/json" \
  -d '{"POT_CCM": 55.3}'
```

**Resultado**: `200 OK` → Servidor accesible.

---

### 2. Regenerar los tokens remotamente (`fetch_tokens_remote.py`)

Se creó y ejecutó un script que:
1. Hace login en el ThingsBoard remoto.
2. Consulta el ID y el `accessToken` de cada uno de los 31 sensores ESAMUR.
3. Sobreescribe el fichero `deploy/ESAMUR/DeviceimportCredentials_ESAMUR.csv` con los tokens correctos.

```bash
ROOT=http://18.185.1.118:9090 python3 fetch_tokens_remote.py
```

**Resultado**: Los 31 dispositivos fueron encontrados y el CSV actualizado.

---

### 3. Lanzar el simulador

```bash
ROOT=http://18.185.1.118:9090 python3 src/dataloader/simulador_sensores.py --client ESAMUR
```

**Resultado**: ✅ Inyección funcionando. Los datos llegan a ThingsBoard en `18.185.1.118` y son visibles en los dashboards.

---

## Resumen de Comandos (en orden)

```bash
# 1. Regenerar tokens del ThingsBoard remoto
ROOT=http://18.185.1.118:9090 python3 fetch_tokens_remote.py

# 2. Lanzar el inyector
ROOT=http://18.185.1.118:9090 python3 src/dataloader/simulador_sensores.py --client ESAMUR

# Opcional: limitar filas o ajustar velocidad
ROOT=http://18.185.1.118:9090 python3 src/dataloader/simulador_sensores.py --client ESAMUR --delay 0.5 --limit 100
```

> [!IMPORTANT]
> Si la IP del servidor cambia, volver a ejecutar `fetch_tokens_remote.py` con la nueva IP antes de lanzar el simulador. Los tokens son propios de cada instancia de ThingsBoard.
