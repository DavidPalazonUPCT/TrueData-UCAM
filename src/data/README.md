# README — Proceso de entrenamiento para un nuevo cliente (Flowguard / CoGNN)

Este documento describe, paso a paso, cómo preparar los datos, lanzar el entrenamiento en Docker con GPU y seleccionar el mejor modelo para un nuevo cliente.

---

## Requisitos previos

* **GPU NVIDIA** con drivers y **NVIDIA Container Toolkit** instalados (para `--gpus all`).
* **Docker** 24+.
* **Python 3.10+** (solo para utilidades locales si fuera necesario).
* Acceso a credenciales de **AWS S3** (si aplica subida/descarga de artefactos):

  * `AWS_ACCESS_KEY_ID`
  * `AWS_SECRET_ACCESS_KEY`
* **Weights & Biases (W&B)** para tracking de experimentos:

  * `WANDB_KEY` (API key)
  * `WANDB_RUN=true` (para habilitar logging)
* Estructura de proyecto ubicada (por defecto) en: `/home/jesuspardo/Flowguard-compose`.

> **Convenciones**
>
> * Reemplaza `CLIENT_NAME` por el identificador del cliente (p.ej., `MCT`).
> * Usa el formato de fecha `YYYYY_MMM_DDD` para `FECHA` (p.ej., `2025Y_10M_13D`).
> * `SWEEP_NAME` recomendado: `COGNN-TRAIN_${FECHA}-type`.

---

## 1) Copiar los datos del cliente

1. Crea una carpeta para el cliente: `src/data/CLIENT_NAME`.
2. Copia el archivo **obligatorio** `data.csv` dentro de esa carpeta.

**Estructura esperada**

```
src/
  data/
    CLIENT_NAME/
      data.csv  # debe llamarse exactamente así
```

---

## 2) Generar dataset procesado

Ejecuta el script de preprocesado (desde la raíz del repo):

```bash
CLIENT=CLIENT_NAME TASK=train python3 src/data/generate_data.py
```

Esto generará los artefactos necesarios para el dataloader en `src/data/CLIENT_NAME`.

---

## 3) Configurar `src/config.json`

Edita las siguientes claves:

```json
{
  "Project_Name": "CLIENT_NAME",
  "Sweep_Name": "COGNN-TRAIN_FECHA-type",
  ...
}
```

Ejemplo:

```json
{
  "Project_Name": "MCT",
  "Sweep_Name": "COGNN-TRAIN_2025Y_10M_13D-type"
}
```

> **Nota:** `Project_Name` debe coincidir con `CLIENT_NAME`.

---

## 4) Construir la imagen Docker de entrenamiento

Desde la raíz del proyecto:

```bash
docker build -f Dockerfile . --tag flowguard-cognn:v1
```

> **Consejo:** si cambias dependencias con frecuencia, usa `--no-cache` para forzar reconstrucción limpia.

---

## 5) Lanzar el entrenamiento

Ejecuta el contenedor con GPU y volúmenes montados:

```bash
docker run --gpus all \
  -v /home/jesuspardo/Flowguard-compose/src/data:/app/data \
  -v /home/jesuspardo/Flowguard-compose/src/dataloader:/app/dataloader \
  -v /home/jesuspardo/Flowguard-compose/src/save:/app/save \
  -e AWS_ACCESS_KEY_ID=AWS-ACCESS \
  -e AWS_SECRET_ACCESS_KEY=AWS-SECRET \
  -e WANDB_KEY=WANDB-KEY \
  -e WANDB_RUN=true \
  -e MODEL=cognn \
  -e CLIENT='CLIENT_NAME' \
  -e TASK=train \
  flowguard-cognn:v1 \
  --save /app/save/ \
  --data /app/data/CLIENT_NAME
```

**Ejemplo mínimo (MCT):**

```bash
docker run --gpus all \
  -v /home/jesuspardo/Flowguard-compose/src/data:/app/data \
  -v /home/jesuspardo/Flowguard-compose/src/dataloader:/app/dataloader \
  -v /home/jesuspardo/Flowguard-compose/src/save:/app/save \
  -e AWS_ACCESS_KEY_ID=xxxx -e AWS_SECRET_ACCESS_KEY=yyyy \
  -e WANDB_KEY=zzzz -e WANDB_RUN=true \
  -e MODEL=cognn -e CLIENT='MCT' -e TASK=train \
  flowguard-cognn:v1 --save /app/save/ --data /app/data/MCT
```

---

## 6) Dónde se guardan los resultados

Los artefactos del entrenamiento se guardan en:

```
src/save/CLIENT_NAME/SWEEP_NAME/RUN_NAME
```

Para evaluar el rendimiento (scores por parámetro), revisa:

```
src/save/CLIENT_NAME/SWEEP_NAME/RUN_NAME/test_re_full.npy
```
---

## 7) Selección del modelo y exportación a `src/models`

Una vez elegido el mejor `RUN_NAME`, copia **todo** su contenido a la ruta de despliegue del modelo:

```
src/models/CLIENT_NAME/MODEL_NAME
```

Ejemplo:

```bash
cp -r src/save/CLIENT_NAME/SWEEP_NAME/RUN_NAME/ src/models/CLIENT_NAME/MODEL_NAME/
```

---

## Estructura de directorios de referencia

```
src/
  config.json
  data/
    CLIENT_NAME/
      data.csv
      ... (artefactos generados)
  dataloader/
    ...
  models/
    CLIENT_NAME/
      MODEL_NAME/
        ... (ficheros del run seleccionado)
  save/
    CLIENT_NAME/
      SWEEP_NAME/
        RUN_NAME/
          test_re_full.npy
          ...
```

---

## Comprobaciones rápidas (checklist)

* [ ] `src/data/CLIENT_NAME/data.csv` existe y **se llama exactamente** `data.csv`.
* [ ] `CLIENT=CLIENT_NAME TASK=train` se ejecutó sin errores y generó artefactos.
* [ ] `src/config.json` actualizado con `Project_Name` y `Sweep_Name` correctos.
* [ ] Imagen `flowguard-cognn:v1` construida.
* [ ] Comando `docker run` usa rutas reales y variables (`AWS_*`, `WANDB_*`).
* [ ] Existen resultados en `src/save/CLIENT_NAME/SWEEP_NAME/RUN_NAME/`.
* [ ] `test_re_full.npy` inspeccionado.
* [ ] Modelo final copiado a `src/models/CLIENT_NAME/MODEL_NAME/`.

---

## Problemas frecuentes y soluciones

* **`data.csv` no encontrado**: verifica nombre exacto y ruta `src/data/CLIENT_NAME/data.csv`.
* **No se guardan los resultados de entrenamiento**: confirma que se están creando las carpetas correspondientes durante la ejecución.
* **Sin GPU dentro del contenedor**: confirma `--gpus all`, drivers y `nvidia-container-toolkit` instalados; comprueba `nvidia-smi` dentro del contenedor.
* **W&B no registra**: valida `WANDB_KEY` y que `WANDB_RUN=true` esté definido.
* **Rutas absolutas distintas**: ajusta los `-v` en el `docker run` la ruta de referencia es: `/home/jesuspardo/Flowguard-compose`.

---

## Ejemplo completo (MCT)

```bash
# 1) Datos
mkdir -p src/data/MCT && cp /ruta/origen/data.csv src/data/MCT/data.csv

# 2) Generación de datos
CLIENT=MCT TASK=train python3 src/data/generate_data.py

# 3) Configuración
# editar src/config.json -> Project_Name: "MCT", Sweep_Name: "COGNN-TRAIN_20251013-type"

# 4) Build
docker build -f Dockerfile . --tag flowguard-cognn:v1

# 5) Entrenamiento
docker run --gpus all \
  -v /home/jesuspardo/Flowguard-compose/src/data:/app/data \
  -v /home/jesuspardo/Flowguard-compose/src/dataloader:/app/dataloader \
  -v /home/jesuspardo/Flowguard-compose/src/save:/app/save \
  -e AWS_ACCESS_KEY_ID=xxxx -e AWS_SECRET_ACCESS_KEY=yyyy \
  -e WANDB_KEY=zzzz -e WANDB_RUN=true \
  -e MODEL=cognn -e CLIENT='MCT' -e TASK=train \
  flowguard-cognn:v1 --save /app/save/ --data /app/data/MCT

# 6) Exportar modelo
cp -r src/save/MCT/COGNN-TRAIN_20251013-type/<RUN_NAME>/ src/models/MCT/<MODEL_NAME>/
```

---

## Notas finales

* Mantén coherencia entre `CLIENT` (env), `Project_Name` (config) y la ruta de datos.
* Estándar de nombres recomendado para `MODEL_NAME`: `cognn_<FECHA>_<tag>`.

