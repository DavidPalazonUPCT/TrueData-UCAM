import argparse
import os
import time
from datetime import datetime

import numpy as np
import pandas as pd
import csv
import json
import torch
import joblib
from utils.anomaly_dd import error_normalizer, load_normalization_stats
from utils.trainer import Trainer
from flask import Flask, request, jsonify
from flask_httpauth import HTTPBasicAuth
from dataloader.sensorsloader import get_sensordata, load_credentials, extract_token, extract_id, extract_keys, extract_telemetry

from utils.stgnn import stgnn

from utils.cognn import CoGNN
from utils.utils_cognn.cognn_helpers import *
from utils.utils_cognn.metrics import MetricType
from utils.utils_cognn.model import ModelType
from utils.utils_cognn.encoders.encoders import DataSetEncoders, PosEncoder
from utils.utils_aws import download_model_from_s3, load_metadata_from_model

import sys


def str_to_bool(value):
    """
        Converts a string or boolean to a boolean value. Supports various string representations for `True` and `False`.

        Parameters:
        ------------
        value: str or bool
            The value to convert, either a string ('true', 'false', etc.) or a boolean.

        Returns:
        --------
        bool:
            The converted boolean value.

        Notes:
        ------
        - Case-insensitive string comparison.
        - `False` values: {'false', 'f', '0', 'no', 'n'}.
        - `True` values: {'true', 't', '1', 'yes', 'y'}.
        """
    if isinstance(value, bool):
        return value
    if value.lower() in {'false', 'f', '0', 'no', 'n'}:
        return False
    elif value.lower() in {'true', 't', '1', 'yes', 'y'}:
        return True
    raise ValueError(f'{value} is not a valid boolean value')


def load_scaling_params(scaler_path):
    print(f"Loading scaling parameters from {scaler_path}")
    sys.stdout.flush()
    scale_params = pd.read_csv(scaler_path)
    scale_params.rename(columns={'Unnamed: 0': 'sensor'}, inplace=True)
    min_vals = scale_params['min'].values
    max_vals = scale_params['max'].values
    return min_vals, max_vals


def apply_minmax_scaling(data, min_vals, max_vals, epsilon=1e-8):
    scaling_factor = max_vals - min_vals
    scaling_factor[scaling_factor == 0] = epsilon
    data = (data - min_vals) / scaling_factor
    return data

def denormalize(data, min_vals, max_vals):
    min_vals = min_vals.reshape(-1, 1)  # Convertir a (num_nodes,1)
    max_vals = max_vals.reshape(-1, 1)  # Convertir a (num_nodes,1)
    return data * (max_vals - min_vals) + min_vals


def get_thresholds_scores():
    with open(f'/app/dataloader/Credenciales.txt') as file:
        credenciales = file.read().strip()
    print(f"Credenciales: {credenciales}")
    # Extract token
    tok, _ = extract_token(credenciales)
    TOKEN = f"Bearer {tok}"
    print(f"TOKEN: {TOKEN}")
    if os.environ['MODEL_NAME'] == 'GDN':
        os.environ['MODEL_THINGSBOARD'] = "M1"
    elif os.environ['MODEL_NAME'] == 'STGNN':
        os.environ['MODEL_THINGSBOARD'] = "M2"
    elif os.environ['MODEL_NAME'] == 'COGNN':
        os.environ['MODEL_THINGSBOARD'] = "M3"
    else:
        raise f"Modelo {os.environ['MODEL_NAME']} no disponible."
    thresholds_device = f"{os.environ['CLIENT']} {os.environ['MODEL_THINGSBOARD']} Thresholds"
    thresholdsID = extract_id(thresholds_device, TOKEN)
    keysList = extract_keys("DEVICE", thresholdsID, TOKEN)
    keysString = ','.join(keysList)
    # Extract telemetry data
    datos = extract_telemetry(1, "DEVICE", thresholdsID, keysString, TOKEN)
    return datos

def load_model(model_path, device, config, args):
    print(f"Loading model from {model_path}")
    sys.stdout.flush()

    if model_path.startswith("s3://"):
        print(f"Inside S3 path: {model_path}")
        sys.stdout.flush()
        local_path = "/app/models/"
        local_path = local_path + os.environ['CLIENT'] + '/model.pth'
        s3_path = model_path
        if download_model_from_s3(model_path, local_path):
            model_config = load_metadata_from_model(s3_path=s3_path)
        else:
            print("Failed to download model from S3")
            model_path = local_path
            model_config_path = local_path + os.environ['CLIENT'] + '/model_metadata.json'
            with open(model_config_path, 'r') as archivo_json:
                model_config = json.load(archivo_json)
    else:
        print(f"Outside S3 path: {model_path}")
        sys.stdout.flush()
        os.environ['MODEL_NAME'] = os.environ['MODEL'].split('-')[0].upper()
        if "EVALUATE" in os.environ:
            model_path = f"{os.environ['MODEL_FOLDER_PATH']}/model.pth"
            model_config = config
        else:
            model_path = f"/app/models/{os.environ['CLIENT']}/{os.environ['MODEL_NAME']}/model.pth"
            model_config = config

    args.num_nodes = int(os.environ['NUM_NODES'])
    args.seq_in_len = int(model_config["seq_in_len"])
    os.environ["threshold"] = str(model_config['threshold'])
    if os.environ['MODEL_NAME'] == 'STGNN':
        model = stgnn(
            gcn_true=str_to_bool(model_config['gcn_true']), buildA_true=str_to_bool(model_config['builda_true']),
            gcn_depth=int(model_config['gcn_depth']), num_nodes=int(model_config['num_nodes']),
            device=device, predefined_A=None, dropout=float(model_config['dropout']),
            subgraph_size=int(model_config['subgraph_size']), node_dim=int(model_config['node_dim']),
            dilation_exponential=int(model_config['dilation_exponential']),
            conv_channels=int(model_config['conv_channels']), layer_norm_affline=True,
            skip_channels=int(model_config['skip_channels']), end_channels=int(model_config['end_channels']),
            seq_length=int(model_config['seq_in_len']), in_dim=int(model_config['in_dim']),
            out_dim=int(model_config['seq_out_len']), layers=int(model_config['layers']),
            propalpha=float(model_config['propalpha']), tanhalpha=int(model_config['tanhalpha']),
            residual_channels=int(model_config['residual_channels']),
        )
    elif os.environ['MODEL_NAME'] == 'COGNN':
        gumbel_args = GumbelArgs(learn_temp=False, temp_model_type=ModelType.GCN, tau0=float(model_config['tau0']),
                                 temp=float(model_config['temp']), gin_mlp_func=lambda x: x)
        env_args = EnvArgs(model_type=ModelType.GCN, num_layers=int(model_config['env_num_layers']), env_dim=int(model_config['env_dim']),
                           layer_norm=True, skip=True, batch_norm=False, dropout=float(model_config['dropout']),
                           act_type=ActivationType.RELU, metric_type=MetricType.ACCURACY, in_dim=int(model_config['env_dim']),
                           out_dim=int(model_config['batch_size']),
                           gin_mlp_func=lambda x: x, dec_num_layers=int(model_config['dec_num_layers']),
                           pos_enc=PosEncoder.NONE,
                           dataset_encoders=DataSetEncoders.NONE)
        action_args = ActionNetArgs(model_type=ModelType.GCN, num_layers=int(model_config['act_num_layers']),
                                    hidden_dim=int(model_config['act_dim']),
                                    dropout=float(model_config['dropout']), act_type=ActivationType.RELU,
                                    env_dim=int(model_config['act_dim']), gin_mlp_func=lambda x: x)
        pool = get_pool()
        model = CoGNN(
            gumbel_args=gumbel_args, env_args=env_args, action_args=action_args, pool=pool, device=device
        )
    engine = Trainer(model, args.learning_rate, args.weight_decay, args.clip, args.step_size1, args.seq_out_len,
                     device, args.scaling_required)
    engine.model.load_state_dict(torch.load(model_path, map_location=device))
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.to(device)
    model.eval()
    return engine


def predict(model, data, device, min_vals, max_vals, scaling_required):
    print("Running prediction...")
    sys.stdout.flush()
    print(f"Predict data input: {data.shape}")
    data = torch.Tensor(data).to(device)
    data = data.transpose(1, 3)  # Adjust dimensions if necessary for your model
    print(f"Predict data reshape: {data.shape}")
    print(f"args.num_nodes: {args.num_nodes}")

    with torch.no_grad():
        if os.environ['MODEL'].split('-')[0] == 'stgnn':
            preds, _ = model(data)
        elif os.environ['MODEL'].split('-')[0] == 'cognn':
            preds = model.pred(input=data)
            # Unificar shape de salida a (N, 1) de forma robusta
            if isinstance(preds, torch.Tensor):
                pass
            else:
                raise RuntimeError("Trainer.pred debe devolver un torch.Tensor en CoGNN")

            # 1) Quita todos los ejes de tamaño 1
            preds = preds.squeeze()

            # 2) Canoniza a (N, T?) o (T, N) o (N,)
            if preds.dim() == 1:
                # Puede venir ya como (N,)
                if preds.shape[0] != args.num_nodes:
                    raise RuntimeError(f"Vector de tamaño inesperado: {tuple(preds.shape)}; N={args.num_nodes}")
                pass  # (N,)
            elif preds.dim() == 2:
                # Dos casos típicos: (N,T) o (T,N)
                if preds.shape[0] == args.num_nodes:
                    # (N, T?)
                    pass
                elif preds.shape[1] == args.num_nodes:
                    # (T, N) -> transpón a (N, T)
                    preds = preds.transpose(0, 1)
                else:
                    raise RuntimeError(f"Forma 2D inesperada: {tuple(preds.shape)}; N={args.num_nodes}, T={args.N}")
            elif preds.dim() == 3:
                # Algún eje sobrante (p.ej., (T,N,?)). Si hay un eje de tamaño 1, exprímelo.
                squeeze_again = False
                for d, s in enumerate(preds.shape):
                    if s == 1:
                        squeeze_again = True
                        break
                if squeeze_again:
                    preds = preds.squeeze()
                    # Re-evalúa con las reglas 2D/1D
                    if preds.dim() == 1:
                        if preds.shape[0] != args.num_nodes:
                            raise RuntimeError(f"Vector inesperado tras squeeze: {tuple(preds.shape)}")
                    elif preds.dim() == 2:
                        if preds.shape[0] == args.num_nodes:
                            pass
                        elif preds.shape[1] == args.num_nodes:
                            preds = preds.transpose(0, 1)
                        else:
                            raise RuntimeError(f"Forma 2D inesperada tras squeeze: {tuple(preds.shape)}")
                    else:
                        raise RuntimeError(f"Forma 3D no reducible: {tuple(preds.shape)}")
                else:
                    raise RuntimeError(f"Forma 3D no soportada (sin ejes de 1): {tuple(preds.shape)}")
            else:
                raise RuntimeError(f"Forma de predicción no soportada: {tuple(preds.shape)}")

            # 3) Si aún hay eje temporal (segunda dimensión > 1), tomar el último t
            if preds.dim() == 2:
                # preds ahora es (N, T?)
                if preds.shape[0] != args.num_nodes:
                    raise RuntimeError(f"Eje N no está en la primera dimensión: {tuple(preds.shape)}")
                preds = preds[:, -1]  # (N,)

            # 4) Deja en (N,1)
            preds = preds.unsqueeze(1)  # (N,1)

        # Print raw predictions
        #print("Raw predictions (preds):", preds.shape)
        #sys.stdout.flush()

        #preds = preds.transpose(1, 3)  # Revert dimensions back after prediction
        #preds = preds.cpu().numpy().squeeze()
        preds = preds.cpu().numpy()

        # Print transposed predictions
        #print("Squeezed predictions (preds):", preds.shape)
        #sys.stdout.flush()

    if scaling_required:
        #preds = preds.cpu().numpy()

        # Print predictions before rescaling
        #print("Predictions before rescaling (preds):", preds)
        sys.stdout.flush()

        #print("Min values:", min_vals)
        preds = (preds * (max_vals - min_vals)) + min_vals

        # Print predictions after rescaling
        print("Predictions after rescaling (preds):", preds.shape)
        sys.stdout.flush()

    # Final predictions after squeezing
    #final_preds = preds.squeeze()
    final_preds = preds
    final_preds[np.isnan(final_preds)] = 0
    final_preds = final_preds.reshape(args.num_nodes, 1)

    print("Shape after squeezing:", final_preds.shape)
    sys.stdout.flush()

    return final_preds


def pca_model(test_error, dim_size=1):
    pca_path = f"/app/models/{os.environ['CLIENT']}/{os.environ['MODEL_NAME']}/pca_model.pkl"
    pca = joblib.load(pca_path)

    print(f"test_error shape 1: {test_error.shape}")
    test_error = test_error.reshape(1, args.num_nodes)
    print(f"test_error shape 2: {test_error.shape}")
    transf_test_error = pca.inverse_transform(pca.transform(test_error))
    test_re_full = np.absolute(transf_test_error - test_error)
    test_re = test_re_full.sum(axis=1)

    return test_re, test_re_full


def scorer(test_obs, test_forecast, num_components, normalization_window, error_batch_size, devicelist, threshold=0.5):
    test_abs = np.absolute(test_obs - test_forecast)

    #print(f"[DEBUG] test_obs: \n {test_obs}")
    #print(f"[DEBUG] test_forecast: \n {test_forecast}")
    #print(f"test_abs shape: \n {test_abs.shape}")
    #print(f"[DEBUG] test_abs: \n {test_abs}")
    #print(f"test_abs shape: \n {test_abs.shape}")

    # Normalize forecast error deviation (assuming functions error_normalizer and error_sw_normalizer are defined)
    median_global, iqr_global = load_normalization_stats(type='iqr')
    test_abs = np.transpose(test_abs)
    test_norm = error_normalizer(test_abs, median_global, iqr_global)
    #test_norm = np.transpose(test_abs)
    #print(f"test_norm shape: {test_norm.shape}")
    #print(f"[DEBUG] median_global shape: \n {median_global.shape}")
    #print(f"[DEBUG] iqr_global shape: \n {iqr_global.shape}")
    #print(f"[DEBUG] test_abs: \n {test_norm}")

    # PCA reconstruction algorithm to score anomaly of each timepoint
    print(f"num_componentes: {num_components}")
    test_re, test_re_full = pca_model(test_norm, num_components)
    np.save(f"/app/dataloader/ETL/scores_full.npy", test_re_full)
    np.save(f"/app/dataloader/ETL/scores.npy", test_re)

    # Node-level anomaly scores
    ##node_anomaly_scores = np.mean(np.absolute(test_norm - test_re), axis=1)  # Example metric: mean absolute error

    # Aggregate node-level scores into a single metric
    ##aggregated_score = np.mean(node_anomaly_scores)  # Example: mean of node-level scores
    os.environ['valorRiesgo'] = str(test_re.item())

    # Determine if an attack is detected
    attack_detected = int(test_re.item() > threshold)

    return test_re, test_re_full, attack_detected


def run_inference_pipeline(args):
    print("Received request at /secure-trigger")
    sys.stdout.flush()

    try:
        print("Retrieving sensor data...")
        time_data_1i = time.time()
        sys.stdout.flush()
        args.client = os.environ["CLIENT"]
        args.model_path = f"/app/models/{os.environ['CLIENT']}/{os.environ['MODEL_NAME']}"
        os.environ['MODEL_FOLDER_PATH'] = args.model_path
        print(f"CLIENT: {os.environ['CLIENT']}")
        if "EVALUATE" in os.environ:
            model_config_path = f"{os.environ['MODEL_FOLDER_PATH']}/model_metadata.json"
            with open(model_config_path, 'r') as archivo_json:
                model_config = json.load(archivo_json)
        else:
            model_config_path = f"/app/models/{os.environ['CLIENT']}/{os.environ['MODEL_NAME']}/model_metadata.json"
            with open(model_config_path, 'r') as archivo_json:
                model_config = json.load(archivo_json)
        args.N = int(model_config["seq_in_len"])
        print(f"seq_in_len (N): {args.N}")

        if "EVALUATE" in os.environ:
            with open(os.environ['TEST_DATA_PATH'], 'r') as file:
                sensordata = json.load(file)
            df_datos = pd.DataFrame.from_dict(sensordata, orient="columns")
            # Para comparar pred(t) con obs(t), necesitamos N entradas + 1 target
            df_datos = df_datos.iloc[0:args.N + 1].copy()
            print(f"sensor data shape: {df_datos.shape}")
            os.environ['NUM_NODES'] = str(df_datos.shape[1] - 1)
            sensordata = df_datos.to_dict()
        else:
            # Pedimos N+1 para poder usar obs real en t
            sensordata = get_sensordata(args.N + 1, args.Nulo, args.Metodo)
        time_data_1f = time.time()
        time_data_1 = time_data_1f - time_data_1i
        print("Time to load data from Thingsboard: {:.2f} seconds".format(time_data_1))

        os.environ['s3_path'] = str(args.model_path)

        print("Sensor data retrieved")
        sys.stdout.flush()

        devices_path = 'data/' + args.client + '/DeviceImport.csv'
        print(f"Loading devices from {devices_path}")
        sys.stdout.flush()
        devices = pd.read_csv(devices_path)
        devicelist = devices['name'].to_list()
        # devicelist = devicelist.array
        # print(f"Loaded devices: {devicelist}")
        sys.stdout.flush()

        ts = [*sensordata["timestamp"].keys()]
        df_sensordata = pd.DataFrame.from_dict(sensordata, orient="columns")
        df_ts_list = df_sensordata['timestamp'].tolist()
        # print("Timestamps from ETL")
        # print(df_ts_list)
        dt_object = datetime.fromtimestamp(float(sensordata["timestamp"][ts[0]]) / 1000.0)

        model = load_model(args.model_path, device, model_config, args)

        inferenceinput = [[] for _ in range(args.N + 1)]
        for dev in devicelist:
            try:
                # Obtenemos los valores de telemetría del sensor
                # ThingsBoard devuelve los datos ordenados por ts DESC (más reciente primero)
                dev_values = list(sensordata[dev].values())
                devinfo = [float(ele) for ele in dev_values]
                
                for i in range(args.N + 1):
                    # Si faltan datos (menos de N+1 puntos), esto lanzará IndexError
                    inferenceinput[i].append(devinfo[i])
            except (KeyError, IndexError):
                # Si el sensor no existe o no tiene suficientes datos, rellenamos con 0.0
                for i in range(args.N + 1):
                    inferenceinput[i].append(0.0)

        infarray_full = np.array(inferenceinput)
        # print(f"Inference input shape: {infarray.shape}")
        # print(infarray_0[-1,:])
        sys.stdout.flush()

        # Normalize
        if "EVALUATE" in os.environ:
            scaler_path = f"{args.scaler_path}"
        else:
            scaler_path = f"/app/models/{os.environ['CLIENT']}/{os.environ['MODEL_NAME']}/{args.scaler_path}"
        min_vals, max_vals = load_scaling_params(scaler_path)
        # Entrada al modelo: las primeras N filas (t−N..t−1)
        infarray_in = infarray_full[:args.N, :]
        infarray = apply_minmax_scaling(data=infarray_in, min_vals=min_vals, max_vals=max_vals)
        #print(f"infarray shape: {infarray.shape}")
        #print(f"[DEBUG] infarray_in: {infarray_in}")
        #print(f"[DEBUG] infarray: {infarray}")
        # for i in range(len(inferenceinput)):
        #    max_val = np.max(np.abs(infarray[i]))
        #    if max_val != 0:  # Prevent division by zero
        #        infarray[i] = infarray[i] / max_val

        infarray = infarray.reshape((1, infarray.shape[0], infarray.shape[1], 1))
        # print(f"Reshaped inference input: {infarray.shape}")
        sys.stdout.flush()

        # print(f"======================")
        # print(f"[DEBUG] data = {infarray}")

        test_pred = predict(model, infarray, device, min_vals, max_vals, args.scaling_required)
        # print("Prediction made, test_pred shape: ", test_pred.shape)
        # print(test_pred)
        # sys.stdout.flush()
        # threshold = 0.9
        threshold = float(os.environ["threshold"])

        # Observación real en t: la fila N (después de normalizar)
        last_row = apply_minmax_scaling(data=infarray_full[args.N:args.N+1, :], min_vals=min_vals, max_vals=max_vals)  # (1, num_nodes)
        test_obs = last_row.reshape(args.num_nodes, 1)
        # print(f"Obs shape: {test_obs.shape}")
        # print(f"Min vals: {min_vals.shape}")
        # print(f"[DEBUG] test_pred = {test_pred}")
        # print(f"======================")
        # print(f"[DEBUG] test_obs = {test_obs}")

        # Unnormalize values
        pred_unnormalized = denormalize(test_pred, min_vals, max_vals)
        real_unnormalized = denormalize(test_obs, min_vals, max_vals)
        abs_unnormalized = np.absolute(real_unnormalized - pred_unnormalized)
        relative_unnormalized = np.abs(
            np.divide(pred_unnormalized - real_unnormalized, pred_unnormalized, where=pred_unnormalized != 0)) * 100
        relative_unnormalized[pred_unnormalized == 0] = 100  # Sustituir los valores donde el denominador es 0
        # Save absolute error as json
        abs_unnormalized = abs_unnormalized.transpose()
        relative_unnormalized = relative_unnormalized.transpose()
        # print(f"abs_unnormalized: {abs_unnormalized}")
        df_abs_unnormalized = pd.DataFrame(abs_unnormalized, columns=devicelist)
        df_abs_unnormalized.to_json('dataloader/ETL/abs_error.json', orient='records', indent=4)
        df_relative_unnormalized = pd.DataFrame(relative_unnormalized, columns=devicelist)
        df_relative_unnormalized.to_json('dataloader/ETL/rel_error.json', orient='records', indent=4)

        # Use the scorer function to get anomaly scores
        test_re, node_anomaly_scores, attack = scorer(
            test_obs=test_obs, test_forecast=test_pred, num_components=args.pca_compo,
            normalization_window=args.normalization_window, error_batch_size=args.error_batch_size,
            devicelist=devicelist, threshold=threshold
        )

        print("Returning attack response...", attack)
        sys.stdout.flush()

        # print("device_list: ", devicelist)
        # sys.stdout.flush()

        # Normalize node-level scores to get probabilities
        # node_anomaly_probabilities = node_anomaly_scores / np.sum(node_anomaly_scores)
        devices_json = devices.to_dict(orient='records')

        # print("node_anomaly_probabilities: ", node_anomaly_probabilities)
        # sys.stdout.flush()

        # Convert NumPy array to a list
        # devicelist_list = devicelist.tolist()
        devicelist_list = devicelist.copy()
        node_anomaly_scores_list = node_anomaly_scores[0].tolist()
        # print(f"node scores: {node_anomaly_scores_list}")
        os.makedirs(f"/app/dataloader/CLIENT/{os.environ['CLIENT']}", exist_ok=True)
        with open(f"/app/dataloader/CLIENT/{os.environ['CLIENT']}/scores.csv", 'a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(node_anomaly_scores_list)

        # Normalize scores
        if "EVALUATE" in os.environ:
            scale_score_path = f"{os.environ['MODEL_FOLDER_PATH']}/score_max.csv"
            scale_score = pd.read_csv(scale_score_path)
            score_max_list = scale_score["score_max"].tolist()
        else:
            #scale_score_path = f"/app/models/{os.environ['CLIENT']}/{os.environ['MODEL_NAME']}/score_max.csv"  # local
            os.environ['ROOT'] = "http://172.25.0.2:9090"
            datos_thresholds = get_thresholds_scores()
            print(f"thressholds scores type: {type(datos_thresholds)}")
            print(f"thressholds scores: {datos_thresholds}")
            sensor_keys = list(datos_thresholds.keys())
            score_max_list = [float(datos_thresholds[k][0]['value']) for k in sensor_keys]
            ## DEBUG ##
            #scale_score_path = f"{os.environ['MODEL_FOLDER_PATH']}/score_max.csv"
            #scale_score = pd.read_csv(scale_score_path)
            #score_max_list = scale_score["score_max"].tolist()
            ## ## ## ##


        normalized_list = [
            min(val / (score_max * 2), 1)  # Replace values greater than 1 with 1
            for val, score_max in zip(node_anomaly_scores_list, score_max_list)
        ]

        # Filter out devices with probabilities below a certain threshold
        threshold_sensor = 0.03

        devices_dict = {device: prob for device, prob in
                        zip(devicelist_list, normalized_list)}  # if prob >= threshold_sensor}

        # Save output as JSON
        out = {
            "attack": int(attack),
            "devices": devices_dict,
            "timestamp": df_ts_list[0],
            "valorRiesgo": float(os.environ['valorRiesgo'])}

        time_data_2i = time.time()
        time_inference = time_data_2i - time_data_1f
        print("Time to calculate inference: {:.2f} seconds".format(time_inference))
        sys.stdout.flush()

        # Guardar el diccionario 'out' como JSON en el archivo
        with open('/app/dataloader/ETL/out.json', 'w') as json_file:
            json.dump(out, json_file, indent=4)

        if "EVALUATE" in os.environ:
            model_dir = os.path.basename(os.environ['MODEL_FOLDER_PATH'].rstrip('/'))
            data_file_name = os.path.basename(os.environ["TEST_DATA_PATH"])
            os.makedirs(f"/app/tests", exist_ok=True)
            results_csv_path = f"/app/tests/{os.environ['CLIENT']}_inference_results.csv"

            row = {
                "timestamp": df_ts_list[0],
                "attack": int(attack),
                "valorRiesgo": float(os.environ['valorRiesgo']),
                "model": model_dir,
                "data_file": data_file_name
            }
            row.update(devices_dict)
            df_result = pd.DataFrame([row])
            if os.path.exists(results_csv_path):
                df_result.to_csv(results_csv_path, mode='a', index=False, header=False)
            else:
                df_result.to_csv(results_csv_path, mode='w', index=False, header=True)
            print(f"[INFO] Resultado guardado en /app/tests/{os.environ['CLIENT']}_inference_results.csv")
            return
        else:
            return jsonify(
                {"attack": int(attack),
                 "devices": devices_dict,
                 "timestamp": df_ts_list[0],
                 "valorRiesgo": float(os.environ['valorRiesgo'])})

    except IndentationError as e:
        print(f"Error: {e}")
        sys.stdout.flush()
        return jsonify({"error": str(e)}), 500


def create_app(args):
    app = Flask(__name__)
    auth = HTTPBasicAuth()

    print("Entering create_app")
    sys.stdout.flush()

    users = {
        "admin": "secret"
    }

    @auth.verify_password
    def verify_password(username, password):
        if username in users and users[username] == password:
            return username

    @app.route('/secure-trigger', methods=['POST'])
    @auth.login_required
    def secure_trigger():
        return run_inference_pipeline(args)

    return app


def parse_arguments():
    parser = argparse.ArgumentParser()

    parser.add_argument('--device', type=str, default='cpu', help='')
    parser.add_argument('--data', type=str, default='./dataloader/ETL/TEST/datos_0.json', help='data path')
    parser.add_argument('--scaling_required', type=str_to_bool, default=False,
                        help='Whether to scale input for model and inverse scale output from model.')
    parser.add_argument('--model_path', type=str, required=True, help='Path to the trained model.')
    parser.add_argument('--scaler_path', type=str, required=True, help='Path to the scaler parameters CSV file.')
    parser.add_argument('--model', type=str, default='cognn', help='Model.')
    parser.add_argument('--client', type=str, default='MCT', help='Client.')
    parser.add_argument('--save', type=str, default='./save/', help='save path')
    parser.add_argument('--runs', type=int, default=1, help='number of runs')
    parser.add_argument('--save_result', type=str, default='', help='path to save forecasting results')
    parser.add_argument('--delays', type=str, default='[0,6,30,60,120,180,360]',
                        help='Early detection delay constraint values')
    parser.add_argument('--batch_size', type=int, default=12, help='batch size')
    parser.add_argument('--learning_rate', type=float, default=3e-4, help='learning rate')
    parser.add_argument('--weight_decay', type=float, default=0.0001, help='weight decay rate')
    parser.add_argument('--clip', type=int, default=10, help='clip')
    parser.add_argument('--step_size1', type=int, default=2500, help='step_size')
    parser.add_argument('--step_size2', type=int, default=100, help='step_size')
    parser.add_argument('--epochs', type=int, default=20, help='')
    parser.add_argument('--print_every', type=int, default=5000, help='')
    parser.add_argument('--dropout', type=float, default=0.1, help='dropout rate')
    parser.add_argument('--buildA_true', type=str_to_bool, default=True,
                        help='whether to construct adaptive adjacency matrix')
    parser.add_argument('--propalpha', type=float, default=0.1, help='prop alpha in graph module')
    parser.add_argument('--tanhalpha', type=float, default=20, help='adj alpha in graph constructor')
    parser.add_argument('--num_split', type=int, default=3, help='number of splits for graphs')
    parser.add_argument('--node_dim', type=int, default=256, help='dim of nodes')
    parser.add_argument('--num_nodes', type=int, default=127, help='number of nodes/variables')
    parser.add_argument('--subgraph_size', type=int, default=15, help='k')
    parser.add_argument('--gcn_true', type=str_to_bool, default=True, help='whether to add graph convolution layer')
    parser.add_argument('--gcn_depth', type=int, default=2, help='graph convolution depth')
    parser.add_argument('--dilation_exponential', type=int, default=1, help='dilation exponential')
    parser.add_argument('--conv_channels', type=int, default=16, help='convolution channels')
    parser.add_argument('--residual_channels', type=int, default=16, help='residual channels')
    parser.add_argument('--skip_channels', type=int, default=32, help='skip channels')
    parser.add_argument('--end_channels', type=int, default=64, help='end channels')
    parser.add_argument('--layers', type=int, default=2, help='number of layers')
    parser.add_argument('--in_dim', type=int, default=1, help='inputs dimension')
    parser.add_argument('--seq_in_len', type=int, default=12, help='input sequence length')
    parser.add_argument('--seq_out_len', type=int, default=1, help='output sequence length')
    parser.add_argument('--normalization_window', type=int, default=None,
                        help='Window size to normalize forecast error.')
    parser.add_argument('--pca_compo', type=int, default=10, help='Number of principal components, L')
    parser.add_argument('--error_batch_size', type=int, default=128,
                        help='Batch processing sliding window normalization')

    parser.add_argument('--N', type=int, default=12, help='Number of past windows to extract')
    parser.add_argument('--Nulo', type=str, default="None", help='Value to fill in for empty/null values')
    parser.add_argument('--Metodo', type=str, default='MEDIANA10', help='Methods available: MEDIANA10, MEDIANA5, MEDIA10, MEDIA5')

    args = parser.parse_args()
    args.delays = list(map(int, args.delays.strip('[]').split(',')))
    return args


if __name__ == '__main__':
    args = parse_arguments()
    args.client = os.environ['CLIENT']
    # Check model used
    model_list = {"stgnn-gat", "cognn"}
    model_used = os.getenv("MODEL")
    if model_used not in model_list:
        raise ValueError(f"Modelo no válido para MODEL: {model_used}. Los modelos permitidos son: {model_list}")
    os.environ['MODEL_NAME'] = os.environ['MODEL'].split('-')[0].upper()
    torch.set_num_threads(8)
    device = torch.device(args.device)
    if "EVALUATE" in os.environ:
        print("[INFO] Modo test (EVALUATE=true)")
        run_inference_pipeline(args)
    else:
        print("[INFO] Modo servidor Flask")
        app = create_app(args)
        app.run(host='0.0.0.0', port=5000, debug=True)
