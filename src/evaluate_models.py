import os
import json
import joblib
import numpy as np
import pandas as pd
import torch
import argparse
import sys
from argparse import ArgumentParser
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import MinMaxScaler
from scipy.spatial.distance import cdist

from utils.trainer import Trainer
from utils.stgnn import stgnn
from utils.cognn import CoGNN
from utils.utils_cognn.cognn_helpers import *
from utils.utils_cognn.model import ModelType
from utils.utils_cognn.metrics import MetricType
from utils.utils_cognn.encoders.encoders import DataSetEncoders, PosEncoder


# Command
'''
python3 src/evaluate_models.py \
  --model_dirs \
        ./src/models/MCT/COGNN \
        ./src/models/MCT_RETRAIN/COGNN_2025Y-06M-16D_09h-09m-02s \
        ./src/save/MCT/RETRAIN_2025Y_06M_13D/_type0_COGNN_1 \
  --test_data ./src/dataloader/ETL/TEST/MCT/datos.json \
  --output ./src/tests
'''


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
    return (data - min_vals) / scaling_factor


def denormalize(data, min_vals, max_vals):
    return data * (max_vals - min_vals) + min_vals


def str_to_bool(value):
    if isinstance(value, bool):
        return value
    if value.lower() in {'false', 'f', '0', 'no', 'n'}:
        return False
    elif value.lower() in {'true', 't', '1', 'yes', 'y'}:
        return True
    raise ValueError(f'{value} is not a valid boolean value')


parser = argparse.ArgumentParser()
parser.add_argument('--model_dirs', nargs='+', required=True, help='Lista de carpetas con modelos a evaluar')
parser.add_argument('--test_data', required=True, help='Ruta al JSON de datos de test')
parser.add_argument('--output', required=True, help='Directorio donde guardar resultados')

parser.add_argument('--device', type=str, default='cuda:0', help='')
parser.add_argument('--data', type=str, default='./dataloader/ETL/TEST/datos_0.json', help='data path')
parser.add_argument('--scaling_required', type=str_to_bool, default=False,
                    help='Whether to scale input for model and inverse scale output from model.')
#parser.add_argument('--model_path', type=str, required=True, help='Path to the trained model.')
#parser.add_argument('--scaler_path', type=str, required=True, help='Path to the scaler parameters CSV file.')
parser.add_argument('--model', type=str, default='cognn', help='Model.')
parser.add_argument('--client', type=str, default='MCT', help='Client.')
parser.add_argument('--save', type=str, default='./save/', help='save path')
parser.add_argument('--runs', type=int, default=1, help='number of runs')
parser.add_argument('--save_result', type=str, default='', help='path to save forecasting results')
parser.add_argument('--delays', type=str, default='[0,6,30,60,120,180,360]',
                    help='Early detection delay constraint values')
parser.add_argument('--batch_size', type=int, default=4, help='batch size')
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

parser.add_argument('--N', type=int, default=5, help='Number of past windows to extract')
parser.add_argument('--Nulo', type=str, default="None", help='Value to fill in for empty/null values')
parser.add_argument('--Metodo', type=str, default='MEDIANA10', help='Methods available: MEDIANA10, MEDIANA5, MEDIA10, MEDIA5')

args = parser.parse_args()

os.environ['CLIENT'] = 'MCT'
os.environ['MODEL'] = 'cognn'
os.environ['TASK'] = 'inference'


def load_model_and_metadata(model_dir, device, args):
    model_path = os.path.join(model_dir, "model.pth")
    metadata_path = os.path.join(model_dir, "model_metadata.json")
    with open(metadata_path, 'r') as f:
        config = json.load(f)

    os.environ['MODEL_NAME'] = os.environ['MODEL'].split('-')[0].upper()
    args.seq_in_len = int(config['seq_in_len'])
    args.seq_out_len = int(config['seq_out_len'])
    args.num_nodes = int(config['num_nodes'])
    os.environ['NUM_NODES'] = str(int(config['num_nodes']))

    if os.environ['MODEL_NAME'] == 'STGNN':
        model = stgnn(
            gcn_true=str_to_bool(config['gcn_true']), buildA_true=str_to_bool(config['builda_true']),
            gcn_depth=int(config['gcn_depth']), num_nodes=int(config['num_nodes']),
            device=device, predefined_A=None, dropout=float(config['dropout']),
            subgraph_size=int(config['subgraph_size']), node_dim=int(config['node_dim']),
            dilation_exponential=int(config['dilation_exponential']),
            conv_channels=int(config['conv_channels']), layer_norm_affline=True,
            skip_channels=int(config['skip_channels']), end_channels=int(config['end_channels']),
            seq_length=int(config['seq_in_len']), in_dim=int(config['in_dim']),
            out_dim=int(config['seq_out_len']), layers=int(config['layers']),
            propalpha=float(config['propalpha']), tanhalpha=int(config['tanhalpha']),
            residual_channels=int(config['residual_channels']),
        )
    elif os.environ['MODEL_NAME'] == 'COGNN':
        gumbel_args = GumbelArgs(learn_temp=False, temp_model_type=ModelType.GCN, tau0=float(config['tau0']),
                                 temp=float(config['temp']), gin_mlp_func=lambda x: x)
        env_args = EnvArgs(model_type=ModelType.GCN, num_layers=int(config['env_num_layers']),
                           env_dim=int(config['env_dim']),
                           layer_norm=True, skip=True, batch_norm=False, dropout=float(config['dropout']),
                           act_type=ActivationType.RELU, metric_type=MetricType.ACCURACY,
                           in_dim=int(config['env_dim']),
                           out_dim=int(config['batch_size']),
                           gin_mlp_func=lambda x: x, dec_num_layers=int(config['dec_num_layers']),
                           pos_enc=PosEncoder.NONE,
                           dataset_encoders=DataSetEncoders.NONE)
        action_args = ActionNetArgs(model_type=ModelType.GCN, num_layers=int(config['act_num_layers']),
                                    hidden_dim=int(config['act_dim']),
                                    dropout=float(config['dropout']), act_type=ActivationType.RELU,
                                    env_dim=int(config['act_dim']), gin_mlp_func=lambda x: x)
        pool = get_pool()
        model = CoGNN(
            gumbel_args=gumbel_args, env_args=env_args, action_args=action_args, pool=pool, device=device
        )
    engine = Trainer(model, config['learning_rate'], config['weight_decay'], config['clip'], config['step_size1'], config['seq_out_len'],
                     device, args.scaling_required)
    engine.model.load_state_dict(torch.load(model_path, map_location=device))
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.to(device)
    model.eval()
    return engine, config


def evaluate_models(model_dirs, test_data_path, output_dir, device):
    os.makedirs(output_dir, exist_ok=True)

    # === Paso 1: Cargar datos desde JSON ===
    with open(test_data_path, 'r') as file:
        raw_data = json.load(file)
    df = pd.DataFrame.from_dict(raw_data)
    df = df.drop(columns='timestamp')
    print(f"✔ Loaded test input: {df.shape[0]} rows, {df.shape[1]} sensors")

    data_array = df.values.astype(np.float32)  # (T, N)
    T, N = data_array.shape

    results = []

    for model_dir in model_dirs:
        print(f"\n▶ Evaluating model at: {model_dir}")

        # === Paso 2: Cargar modelo + metadata
        model, config = load_model_and_metadata(model_dir, device, args)

        args.client = model_dir.split('/')[3]
        devices_path = f"./src/data/{args.client}/DeviceImport.csv"
        print(f"Loading devices from {devices_path}")
        devices = pd.read_csv(devices_path)
        devicelist = devices['name'].to_list()

        edge_index = torch.tensor(np.load(f"{model_dir}/learned_edge_index.npy"), dtype=torch.long).to(device)

        # === Paso 3: Cargar PCA + score_max + min/max
        pca = joblib.load(os.path.join(model_dir, "pca_model.pkl"))

        score_max_df = pd.read_csv(os.path.join(model_dir, "score_max.csv"))
        score_max_dict = dict(zip(score_max_df["name"], score_max_df["score_max"]))

        min_vals, max_vals = load_scaling_params(f"./src/data/{os.environ['CLIENT']}/scale_params.csv")

        # === Paso 4: Normalización previa del input
        normalized_array = apply_minmax_scaling(data_array, min_vals, max_vals)  # (T, N)
        x_test = normalized_array.reshape(1, T, N, 1)  # (B=1, T, N, C=1)

        # === Paso 5: Inferencia
        x = torch.tensor(x_test, dtype=torch.float32).to(device).transpose(1, 3)  # (B, C, N, T)
        with torch.no_grad():
            if os.environ['MODEL_NAME'] == 'STGNN':
                pred, _ = model(x)
            elif os.environ['MODEL_NAME'] == 'COGNN':
                pred = model.pred(input=x)
                pred = pred[0, :, :, :].squeeze(0)
        pred = pred.numpy().squeeze()  # (T, N)
        target = x_test.squeeze()[-1:, :]  # (T, N)
        #print(f"[DEBUG] pred = {pred}")
        print(f"======================")
        #print(f"[DEBUG] target = {target}")

        # === Paso 6: Desnormalizar predicciones y observaciones
        pred_unnorm = denormalize(pred, min_vals, max_vals)
        target_unnorm = denormalize(target, min_vals, max_vals)

        #print(f"[DEBUG] pred.shape = {pred.shape}")
        #print(f"[DEBUG] target.shape = {target.shape}")
        #print(f"[DEBUG] pred_unnorm.shape = {pred_unnorm.shape}")
        #print(f"[DEBUG] target_unnorm.shape = {target_unnorm.shape}")

        # === Paso 7: Error
        error = np.abs(pred_unnorm - target_unnorm)  # (T, N)
        error_flat = error[-1:, :]  # (1, N)
        #print(f"[DEBUG] error_flat shape: {error_flat.shape}")
        # === Paso 7.1: Error relativo por sensor
        with np.errstate(divide='ignore', invalid='ignore'):
            relative_error = np.abs((pred_unnorm - target_unnorm) / pred_unnorm) * 100
            relative_error = np.nan_to_num(relative_error, nan=100.0, posinf=100.0, neginf=100.0)

        # === Paso 8: PCA + Score
        error_proj = pca.transform(error_flat)
        error_recons = pca.inverse_transform(error_proj)
        residual = np.abs(error_flat - error_recons)
        score_max_array = np.array([score_max_dict[sensor] for sensor in devicelist])  # shape: (51,)

        #print(f"[DEBUG] residual.shape = {residual.shape}")
        #print(f"[DEBUG] score_max.shape = {score_max_array.shape}")

        score = residual.sum(axis=1)       # (1,)
        score_norm = residual / score_max_array  # (N,)

        # === Paso 9: Métricas
        mae = mean_absolute_error(target_unnorm, pred_unnorm.reshape(1, -1))
        rmse = mean_squared_error(target_unnorm, pred_unnorm.reshape(1, -1), squared=False)

        #print(f"[DEBUG] score.shape = {score.shape}")
        #print(f"[DEBUG] score_norm.shape = {score_norm.shape}")
        #print(f"[DEBUG] mae.shape = {mae.shape}")
        #print(f"[DEBUG] rmse.shape = {rmse.shape}")

        print(f"[{os.path.basename(model_dir)}] "
              f"MAE: {float(mae):.5f} | "
              f"RMSE: {float(rmse):.5f} | "
              f"Score: {float(score[0]):.4f} | ")

        row = {
            "model": os.path.basename(model_dir),
            "mae": mae,
            "rmse": rmse,
            "score": float(score[0])
        }
        # Añadir cada score normalizado por sensor con su nombre
        for i, device_name in enumerate(devicelist):
            row[f"score_{device_name}"] = float(score_norm[0, i])
            row[f"rel_error_{device_name}"] = float(relative_error[0, i])
        results.append(row)

    df = pd.DataFrame(results)
    output_csv = os.path.join(output_dir, "model_comparison.csv")
    df.to_csv(output_csv, index=False)
    print(f"\n✅ Comparison saved to: {output_csv}")



evaluate_models(
    model_dirs=args.model_dirs,
    test_data_path=args.test_data,
    output_dir=args.output,
    device=torch.device("cuda" if torch.cuda.is_available() else "cpu")
)

