# Guía de Despliegue y Operación — TrueData (módulo base)

Esta guía documenta los pasos para desplegar el módulo base de TrueData
(ThingsBoard + Node-RED + pipeline de despliegue + simulador) en una máquina
local o servidor.

## 1. Requisitos Previos

- Docker Engine y Docker Compose v2.
- Acceso a una terminal con permisos de superusuario (`sudo`) para ajustar
  permisos de volúmenes.
- Python 3.9+ con `pandas` y `requests` para los scripts de `deploy/` y el
  simulador.

---

## 2. Preparación del Entorno

### 2.1. Creación de la red Docker

Subred dedicada para asignar IPs estáticas a los servicios.

```bash
docker network create --driver=bridge --subnet=172.25.0.0/24 truedata_iot_network
```

### 2.2. Permisos de ThingsBoard

ThingsBoard requiere permisos específicos en sus volúmenes para inicializar
PostgreSQL.

```bash
cd truedata-thingsboard
mkdir -p tb-data/db tb-logs
sudo chmod -R 777 tb-data
sudo chmod 750 tb-data/db
```

### 2.3. Configuración de Node-RED

`truedata-nodered/settings.js` se monta directamente en el contenedor mediante
volumen (`./settings.js:/data/settings.js:ro`). Edita `adminAuth` y
`credentialSecret` antes de levantar el servicio.

---

## 3. Despliegue de Infraestructura

```bash
cd truedata-thingsboard && docker compose up -d
cd ../truedata-nodered  && docker compose up -d
```

**Verificación:**
- `http://localhost:9090` → ThingsBoard (puede tardar 3–5 min en el primer arranque).
- `http://localhost:1880` → Node-RED.

---

## 4. Inicialización del Cliente

`deploy/Client.json` define el cliente y modelo. Tras revisarlo, lanza el
script maestro:

```bash
python3 deploy/env_client.py
```

Encadena los scripts numerados de `deploy/`: configuración general, niveles
de criticidad, dispositivos en TB, flujos ETL en Node-RED y subida de
thresholds. Detalle por script en el `README.md` raíz.

---

## 5. Modo DEMO: Simulador

Para inyectar telemetría sintética contra el TB local:

```bash
python3 simulator/simulador_sensores.py --client ESAMUR
```

Documentación detallada en `SIMULATION_GUIDE.md` y `INJECTION_SETUP.md`.

---

## 6. Acceso a Servicios

| Servicio | URL | Usuario por defecto | Password por defecto |
| :--- | :--- | :--- | :--- |
| **ThingsBoard** | http://localhost:9090 | `tenant@thingsboard.org` | `tenant` |
| **Node-RED**    | http://localhost:1880 | `tenant`                 | `tenantairtrace`     |

> [!IMPORTANT]
> Estas son credenciales por defecto del scaffold UCAM. Cámbialas en
> `settings.js` (Node-RED) y vía la API de TB antes de cualquier despliegue
> real.
