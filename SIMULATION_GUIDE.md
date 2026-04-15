# Guía del Simulador de Inyección de Datos (Sensor Simulator)

Este simulador permite inyectar datos históricos en ThingsBoard como si fueran lecturas de sensores en tiempo real. Es la herramienta principal para validar que los flujos de Node-RED, el motor de inferencia y los dashboards funcionan correctamente.

## Ubicación del Script
El script se encuentra en: `simulator/simulador_sensores.py`

---

## 1. Funcionamiento Interno
El simulador realiza los siguientes pasos de forma automática:
1.  **Mapeo de Tokens**: Busca los `accessToken` de cada sensor en el archivo generado durante el despliegue (`deploy/{CLIENT}/DeviceimportCredentials_{CLIENT}.csv`).
2.  **Lectura de Dataset**: Carga el archivo `src/data/{CLIENT}/data.csv`.
3.  **Transmisión HTTP**: Envía peticiones POST al endpoint de telemetría de ThingsBoard (`/api/v1/{token}/telemetry`) para cada sensor y cada fila del dataset.

---

## 2. Requisitos Previos
1.  **ThingsBoard Activo**: La instancia de ThingsBoard debe estar corriendo (Docker).
2.  **Configuración de Cliente**: Debes haber ejecutado el script de despliegue (`python3 deploy/env_client.py`) para que existan los dispositivos y sus tokens.
3.  **Librerías Python**: Asegúrate de tener instalado `pandas` y `requests`.

---

## 3. Comandos de Uso

### Uso Básico (ESAMUR)
Para simular el flujo de datos de ESAMUR con el intervalo por defecto (1 segundo):
```bash
python3 simulator/simulador_sensores.py --client ESAMUR
```

### Parámetros Disponibles
| Parámetro | Descripción | Valor por Defecto |
| :--- | :--- | :--- |
| `--client` | Nombre del cliente (usado para localizar CSVs). | `ESAMUR` |
| `--delay` | Segundos de espera entre cada envío de fila completa. | `1.0` |
| `--limit` | Número máximo de filas a inyectar (útil para pruebas cortas). | `None` (Todas) |

### Ejemplo: Simulación Lenta (Prueba de Dashboards)
Para inyectar solo 10 filas con un intervalo de 5 segundos entre ellas:
```bash
python3 simulator/simulador_sensores.py --client ESAMUR --delay 5 --limit 10
```

---

## 4. Verificación
Para confirmar que el simulador está funcionando:
1.  **Consola**: El script te informará de cada fila enviada y de posibles fallos de conexión.
2.  **ThingsBoard**: Ve a *Device Groups* -> *All* -> Elige un sensor (ej. `TURB1`) -> Pestaña *Latest Telemetry*. Verás cómo los valores cambian según el CSV.
3.  **Node-RED**: Si tienes los flujos activos, verás cómo los datos inyectados disparan los procesos ETL y posteriormente el servicio de inferencia.

> [!TIP]
> Si ThingsBoard no está en `localhost:9090`, puedes definir la URL base usando la variable de entorno `ROOT`:
> `export ROOT=http://mi-ip-servidor:9090 && python3 simulator/simulador_sensores.py`
