import os
import requests
import subprocess
import sys
import time


def config_env_client():
    # Step 1: General configuration
    print("=====::: STEP 1: General configuration :::=====")
    sys.stdout.flush()
    try:
        subprocess.run(["python3", "deploy/1_Configuracion_General.py"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error while running 1_Configuracion_General.py: {e}")
        sys.stdout.flush()
        return

    # Step 2: Upload critical levels
    print("=====::: STEP 2: Upload critical levels to Thingsboard :::=====")
    sys.stdout.flush()
    try:
        subprocess.run(["python3", "deploy/1.1_Subir_Niveles_Criticidad_Inicial_Bulk.py"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error while running 1.1_Subir_Niveles_Criticidad_Inicial_Bulk.py: {e}")
        sys.stdout.flush()
        return

    # Step 3: Upload client's devices to Thingsboard
    print("=====::: STEP 3: Upload client's devices to Thingsboard :::=====")
    sys.stdout.flush()
    try:
        subprocess.run(["python3", "deploy/2_Crear_Entorno_Cliente_ThingsBoard.py"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error while running 2_Crear_Entorno_Cliente_ThingsBoard.py: {e}")
        sys.stdout.flush()
        return

    # Step 4: Upload client's flow to NodeRed
    print("=====::: STEP 4: Upload client's flow to NodeRed :::=====")
    sys.stdout.flush()
    try:
        subprocess.run(["python3", "deploy/2.2_Crear_ETL_NodeRed_Cliente.py"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error while running 2.2_Crear_ETL_NodeRed_Cliente.py: {e}")
        sys.stdout.flush()
        return

    # Step 5: Upload model's thresholds to Thingsboard
    print("=====::: STEP 5: Upload model's thresholds to Thingsboard :::=====")
    sys.stdout.flush()
    try:
        subprocess.run(["python3", "deploy/4_Subir_thresholds.py"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error while running 4_Subir_thresholds.py: {e}")
        sys.stdout.flush()
        return

if __name__ == "__main__":
    print("Setting the client environment on Thingsboard and NodeRed...")
    sys.stdout.flush()
    os.environ['ROOT'] = "http://172.25.0.2:9090"
    config_env_client()
    print("Configuration completed.")
