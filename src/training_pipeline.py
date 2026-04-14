import os
import subprocess
import sys
import time
import shutil
from utils.util import get_latest_model_folder
from datetime import datetime
from dataloader.sensorsloader_local import *

# Environment
os.environ['AWS_ACCESS_KEY_ID'] = "X"
os.environ['AWS_SECRET_ACCESS_KEY'] = "X"
os.environ['AWS_DEFAULT_REGION'] = "X"
os.environ['WANDB_KEY'] = "X"
os.environ['WANDB_RUN'] = "false"
os.environ['TASK'] = "re-train"
os.environ['ROOT'] = "http://localhost:9090"

# command
#  MODEL="cognn" CLIENT="MCT_RETRAIN" python3 src/training_pipeline.py
#  docker build -f DockerfileTrainPipeline . --tag flowguard-compose-retrain:v1
#  docker run --gpus all -v /home/jesuspardo/Flowguard-compose/src/data:/app/data -v /home/jesuspardo/Flowguard-compose/src/dataloader:/app/dataloader -v /home/jesuspardo/Flowguard-compose/src/models:/app/models -v /home/jesuspardo/Flowguard-compose/src/save:/app/save -e AWS_ACCESS_KEY_ID=X -e AWS_SECRET_ACCESS_KEY=X -e WANDB_KEY=X -e WANDB_RUN=false -e MODEL=cognn -e CLIENT='MCT_RETRAIN' -e TASK=re-train flowguard-compose-retrain:v1 --save /app/save/ --data /app/data/MCT_RETRAIN

def retrain_model():
    # Step 1: Load new data from Thingsboard
    '''print("=======================================================")
    print("=====::: STEP 1: Loading data from Thingsboard :::=====")
    sys.stdout.flush()
    try:
        sensordata_check = get_sensordata(N=10800, Nulo="0", Metodo="MEDIANA10")
    except subprocess.CalledProcessError as e:
        print(f"Error while running get_sensordata: {e}")
        sys.stdout.flush()
        return
        '''

    # Step 2: Generate data
    print("========================================================")
    print("=======::: STEP 2: Generate data for training :::=======")
    sys.stdout.flush()
    time_generate_start = time.time()
    env_vars = os.environ.copy()
    #print(f"Environment variables: {env_vars}")
    try:
        generate_data_process = subprocess.run(["python3", "/app/data/generate_data.py"], env=env_vars, check=True)
        time_generate_end = time.time()
        time_generate_total = time_generate_end - time_generate_start
        print(f"Time to generate data: {time_generate_total:.2f} seconds")
        sys.stdout.flush()
    except subprocess.CalledProcessError as e:
        print(f"Error while running generate_data.py: {e}")
        sys.stdout.flush()
        return


    # Step 3: Train the model
    print("======================================================")
    print("============::: STEP 3: Training model :::============")
    sys.stdout.flush()
    time_train_start = time.time()
    try:
        train_model_process = subprocess.run(
            [
                "python3",
                "/app/run.py",
                "--save", "/app/save/",
                "--data", f"/app/data/{os.environ['CLIENT']}"
            ], env=env_vars, check=True)
        time_train_end = time.time()
        time_train_total = time_train_end - time_train_start
        print(f"Training completed.")
        sys.stdout.flush()

        '''# Update model
        model_last_folder = get_latest_model_folder(base_path=f"src/models/{os.environ['CLIENT']}", model=os.environ['MODEL_NAME'])
        with open(f"src/models/{os.environ['CLIENT_0']}/{os.environ['MODEL_NAME']}/model_metadata.json", "r") as f:
            data = json.load(f)
            validation_rmse_old = data.get("Validation rmse", None)
        with open(f"{model_last_folder}/model_metadata.json", "r") as f:
            data = json.load(f)
            validation_rmse_new = data.get("Validation rmse", None)
        if validation_rmse_new < validation_rmse_old:
            new_folder = f"{model_last_folder}"                   # Carpeta de origen
            old_folder = f"src/models/{os.environ['CLIENT_0']}"   # Carpeta de destino
            stop_inference_process()                              # Detener inferencia antes de entrenar
            copy_folder(new_folder, old_folder)
            start_inference_process()                             # Reiniciar inferencia después de entrenar

'''
    except subprocess.CalledProcessError as e:
        print(f"Error while running run.py: {e}")
        sys.stdout.flush()
        return

# Function to update model files
def copy_folder(new_folder, old_folder):
    try:
        for item in os.listdir(old_folder):
            s = os.path.join(new_folder, item)
            d = os.path.join(old_folder, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)  # Copia subdirectorios y su contenido
            else:
                shutil.copy2(s, d)  # Copia los archivos
        # Registrar en el log
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"{timestamp} - Model [{os.environ['MODEL_NAME']}] updated from {new_folder}\n"
        LOG_FILE = f"src/models/{os.environ['CLIENT_0']}/update_log.txt"
        with open(LOG_FILE, "a") as log_file:
            log_file.write(log_entry)
        print(f"Contents copied from {new_folder} to {old_folder}")
    except Exception as e:
        print(f"Error copying folder: {e}")

# Function to stop model inference
def stop_inference_process():
    try:
        # Buscar el proceso en segundo plano por nombre
        process_name = "python3 inference_ETL.py"
        result = subprocess.run(["ps", "aux"], capture_output=True, text=True)
        # Filtrar la salida para encontrar el PID del proceso
        for line in result.stdout.splitlines():
            if process_name in line:
                pid = int(line.split()[1])  # El PID está en la segunda columna
                print(f"Stopping inference process with PID {pid}...")
                subprocess.run(["kill", "-9", str(pid)], check=True)
                print(f"Inference process stopped successfully.")
                return True
        print(f"No running process found for {process_name}.")
        return False
    except Exception as e:
        print(f"Error stopping process: {e}")
        return False

# Function to strat model inference
def start_inference_process():
    try:
        print("Starting inference process again...")
        subprocess.Popen(
            f"nohup env MODEL='cognn' CLIENT={os.environ['CLIENT_0']} ROOT={os.environ['ROOT']} python3 src/dataloader/inference_ETL.py > output_log 2>&1 &",
            shell=True)
        print("Inference process started.")
    except Exception as e:
        print(f"Error starting inference process: {e}")

if __name__ == "__main__":
    os.environ['CLIENT_0'] = os.environ['CLIENT'].split('_')[0]
    os.environ['MODEL_NAME'] = os.environ['MODEL'].split('-')[0].upper()
    #print("Waiting for 2:00 AM to start training...")
    sys.stdout.flush()

    retrain_model()
    '''while True:
        retrain_model()
        print("Waiting 1 hour before next training...")
        time.sleep(3600)  # Esperar 1 hora antes de ejecutar el siguiente entrenamiento

    while True:
        now = datetime.now()
        if now.hour == 2:
            print(f"Starting training at {now.strftime('%Y-%m-%d %H:%M:%S')}")
            sys.stdout.flush()
            retrain_model()
            print("Training finished. Exiting script.")
            sys.stdout.flush()
            break  # Sale después de entrenar

        time.sleep(300)  # Revisa la hora cada 5 minutos
        '''
