import subprocess
import time
import os

# Comando
# MODEL='cognn' CLIENT='MCT' ROOT='http://localhost:9090' python3 src/dataloader/inference_ETL.py

def ETL_inference():
    # Step 1: Run the curl command and save the output
    print("Running curl command...")
    time_data_2i = time.time()
    env_vars = os.environ.copy()

    # Define el comando curl
    curl_command = [
        "curl", "-X", "POST", "http://localhost:5000/secure-trigger",
        "-u", "admin:secret"
    ]

    # Ejecutar el comando curl con las variables de entorno
    subprocess.run(curl_command, env=env_vars)

    time_data_2f = time.time()
    time_data_2 = time_data_2f - time_data_2i
    print("Time to make POST request and save output: {:.2f} seconds".format(time_data_2))

    # Step 2: Send data to ETL
    print("Sending output to Thingsboard...")
    time_data_3i = time.time()
    output_to_ETL = subprocess.run(["python3", "src/dataloader/outdata_to_ETL.py"], env=env_vars)
    time_data_3f = time.time()
    time_data_3 = time_data_3f - time_data_3i
    print("Time to send model's inference results: {:.2f} seconds".format(time_data_3))

if __name__ == "__main__":
    time.sleep(2)
    ETL_inference()
    '''
    while True:
        time.sleep(2)
        ETL_inference()
    '''