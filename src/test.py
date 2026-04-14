import subprocess
import os
import sys


# Rutas absolutas o relativas de modelos y archivos de datos
model_paths = [
    #"/app/save/MCT/TRAIN2_2025Y_06M_19D/_num_split3_COGNN_1",
    "/app/save/MCT/TRAIN3_2025Y_06M_23D/_batch_size20_COGNN_1",
    #"/app/save/MCT/TRAIN4_2025Y_06M_23D/_batch_size50_COGNN_1",
    #"/app/save/MCT/TRAIN4_2025Y_06M_23D/_batch_size80_COGNN_1",
    #"/app/save/MCT/TRAIN4_2025Y_06M_23D/_batch_size100_COGNN_1",
]

data_paths = [
    "/app/dataloader/ETL/TEST/MCT/datos_1.json"
]

# Parámetros comunes
client = "MCT"
model_versions = "cognn"
results_dir = "tests/inference_results"
# Iterar sobre combinaciones datos-modelos
for data_path in data_paths:
    for model_path in model_paths:
        print(f"\n🧠 Ejecutando inferencia para modelo: {model_versions} con datos: {data_path}")
        sys.stdout.flush()
        # Construimos comando de ejecución
        env = os.environ.copy()
        env["EVALUATE"] = "true"
        env["TASK"] = "inference"
        env["CLIENT"] = client
        env["MODEL"] = model_versions
        env["TEST_DATA_PATH"] = data_path
        env["MODEL_FOLDER_PATH"] = model_path

        cmd = [
            "python3", "inference.py",
            "--device", "cpu",
            "--scaler_path", model_path + "/scale_params.csv",
            "--scaling_required", "False",
            "--model_path", "local"
        ]

        # Llamar al script de inferencia
        result = subprocess.run(cmd, env=env, stdout=sys.stdout, stderr=sys.stderr)


