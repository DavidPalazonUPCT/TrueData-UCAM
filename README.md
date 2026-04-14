
# FlowGuard Compose

This repository contains the inference code for the FlowGuard project. Node-RED and ThingsBoard have been separated into their own directories for independent deployment.

## Service Architecture

The system is split across three docker-compose files sharing the external network `flowguard-compose_iot_network` (172.25.0.0/24):

| Directory | Services | IP | Port |
|---|---|---|---|
| `truedata-thingsboard/` | ThingsBoard + PostgreSQL | 172.25.0.2, 172.25.0.23 | 9090, 1883, 7070, 5432 |
| `truedata-nodered/` | Node-RED | 172.25.0.3 | 1880 |
| `.` (root) | Inference Service | 172.25.0.4 | 5000 |

For detailed guides on each service, see:
- [Node-RED Guide](truedata-nodered/README.md)
- [ThingsBoard Guide](truedata-thingsboard/README.md)

## Project structure

```
deploy/
images/
src/
   aggregation_files/
   data/
   dataloader/
   models/
   utils/
   config.json
   inference.py
   run.py
truedata-nodered/
   docker-compose.yml
   settings.js
   README.md
truedata-thingsboard/
   docker-compose.yml
   README.md
DockerfileInferenceCPU
docker-compose.yml
```

## Setup and Deployment

### Step 0: Create network.

First, create the external network shared by all services.

```sh
docker network create --driver=bridge --subnet=172.25.0.0/24 flowguard-compose_iot_network
```

### Step 1: Start ThingsBoard (must be first).

```sh
cd truedata-thingsboard
docker compose up -d
```

Wait for ThingsBoard to be ready (check `http://localhost:9090`).

If you get a permissions error in `tb-data/db`:

```sh
sudo chmod -R 777 tb-data
sudo chmod 750 tb-data/db
```

Then restart: `docker compose up -d`

### Step 2: Start Node-RED.

```sh
cd truedata-nodered
docker compose up -d
```

The `settings.js` file is automatically mounted into the container. No manual copy needed.

Check `http://localhost:1880` is accessible.

### Step 3: Start the Inference Service.

From the project root:

```sh
docker compose up --build -d
```

### Step 4: Configure Nodered and Thingsboard.

Make sure that "Client.json" (inside "/deploy" folder) has the name of the client and 
the model that we are going to use. Check the urls in the scripts inside deploy folder. 
Run the following scripts:
- Deploy the aggregation flows in Nodered:
   ```sh
   python3 deploy/1_Configuracion_General.py
   ```
- Send the values of the critical levels to Thingsboard (bucket):
   ```sh
   python3 deploy/1.1_Subir_Niveles_Criticidad_Inicial_Bulk.py
   ```
- Create buckets of the devices in Thingsboard:
   ```sh
   python3 deploy/2_Crear_Entorno_Cliente_ThingsBoard.py
   ```
- Deploy the flows for this client in Nodered:
   ```sh
   python3 deploy/2.2_Crear_ETL_NodeRed_Cliente.py
   ```

- Deploy all with 1 script:
    ```sh
   python3 deploy/env_client.py
   ```  
  
- **Error sending flows to nodered:**

If you run the scripts in the container environment you have to use the functions 
"crear_flow_nodered" and "update_flow_nodered" without the TOKEN variable. You just have to 
change last lines in scripts "1_Configuracion_General.py" and "2.2_Crear_ETL_NodeRed_Cliente.py".

### Optional: Modify critical levels
- Get critical levels:
   ```sh
   python3 deploy/3_Solicitar_Niveles_Criticidad.py
   ```
- Modify values of the critical levels. {MODEL, LEVEL, VALUE} are environment variables That specify the model, 
the critical level that you want to modify and the new value that you want to set for that critical level. 
   ```sh
   MODEL='M3' LEVEL=<LEVEL> VALUE=<VALUE> python3 /deploy/3.1_Modificar_Niveles_Criticidad.py
   ```

## Execute inference periodically

Now we are going to run a python script that will do the inference each minute.

   ```sh
   MODEL='cognn' CLIENT='MCT' ROOT='http://localhost:9090' python3 src/dataloader/inference_ETL.py
   ```
To run it on background:
- Find inference process
    ```sh
   ps aux | grep inference_ETL.py
    ```

- Stop inference process
    ```sh
   kill -9 <PID>
    ```

- Run it on background
    ```sh
   nohup env MODEL="cognn" CLIENT="MCT" ROOT="http://3.66.4.174:9090" python3 src/dataloader/inference_ETL.py > output_log 2>&1 &
    ```

(CLIENT variable is the name of the client, and MODEL can be {stgnn-gat, cognn})






