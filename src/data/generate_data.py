# # Pre-processing dataset
# ---

# Command:
# CLIENT=<CLIENT_NAME> TASK=train python3 src/data/generate_data.py

# ## Import packages and dataset
#
import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
import os
import json

# ##Client path
client = os.environ['CLIENT']  # Client
actual_path = os.getcwd()
data_path = "src/data/" + client + "/data"  # Dataset path
output_dir = "src/data/" + client  # Output directory (folder)
if "_RETRAIN" in client:
    data_path = "/app/data/" + client + "/data"
    output_dir = "/app/data/" + client

print(f"CLIENT: {client}")
# print(f"Actual path: {actual_path}")
# print(f"Data path: {data_path}")
print(f"Output directory: {output_dir}")

# Verificar si el directorio de datos existe y listar su contenido
if os.path.exists(f"{output_dir}"):
    print(f"Directory {output_dir} found.")
    # print(os.listdir(f"/app/data/{client}"))  # Esto listará las carpetas y archivos en el directorio
else:
    print(f"Error: Directory {output_dir} not found.")
    exit()  # Salir si el directorio no existe

if "_RETRAIN" in client:
    file_path = data_path + ".csv"
else:
    # ## Check data file extension
    print(f"Checking data directory: {output_dir}")
    print("Files in directory:", os.listdir(output_dir))
    file_extensions = ['.xlsx', '.csv', '.json']  # List of supported extension
    file_path = None
    for ext in file_extensions:
        if os.path.exists(f"{output_dir}/data{ext}"):
            file_path = data_path + ext
            break


# ## Process Data

# ### Process Training Data

# __Skip null rows in the dataset.__
def rows_to_skip(file_path, sheet=0):
    # Check if the file extension is .xlsx
    if file_path.endswith('.xlsx'):
        preview = pd.read_excel(file_path, sheet_name=sheet, header=None)
    elif file_path.endswith('.csv'):
        preview = pd.read_csv(file_path, header=None)
    elif file_path.endswith('.json'):
        preview = pd.read_json(file_path, header=None)
    # Start checking from row 0, looking for the first non-null row in column 3
    for i in range(len(preview)):
        row = preview.iloc[i]
        if pd.notnull(row[2]):  # Check if column 3 (index 2) is not null
            return i  # Return the index of the first non-null row
    return 0  # If no valid row is found, return 0 (no rows to skip)


number_rows_skipped = rows_to_skip(file_path)
print("Number of skiped rows: {}".format(number_rows_skipped))

if file_path:
    file_extension = os.path.splitext(file_path)[1]
    if file_extension == '.xlsx':
        data_0 = pd.read_excel(file_path, skiprows=number_rows_skipped)
    elif file_extension == '.csv':
        data_0 = pd.read_csv(file_path, skiprows=number_rows_skipped, low_memory=False)
    elif file_extension == '.json':
        data_0 = pd.read_json(file_path, skiprows=number_rows_skipped)
    else:
        raise ValueError(f"Not supported extension: {file_extension}")
else:
    raise FileNotFoundError("File with the specified extensions was not found.")

# Identify datetime column and drop it.
data_0 = data_0.drop([col for col in data_0.columns if pd.api.types.is_datetime64_any_dtype(data_0[col])], axis=1)

# __Management of dataset's null values.__
empty_cols = [col for col in data_0.columns if data_0[col].isnull().all()]
data_0[empty_cols] = data_0[empty_cols].fillna(0)

for i in data_0.columns[data_0.isnull().any(axis=0)]:  # ---Applying Only on variables with NaN values
    data_0[i] = data_0[i].fillna(data_0[i].mean())
if "timestamp" in data_0.columns:
    data_0 = data_0.drop(columns="timestamp")
if "Fecha" in data_0.columns:
    data_0 = data_0.drop(columns="Fecha")

# __Transform categorical variables.__
status_map = {'Active': 1, 'Inactive': 0}
columns_to_transform = data_0.select_dtypes(include=['object']).columns
# Aplicar el mapeo a todas las columnas relevantes
data_0[columns_to_transform] = data_0[columns_to_transform].apply(
    lambda x: x.map(status_map) if x.name in columns_to_transform else x)

# __Create files: 'scale_params', 'fix_values' and 'median_values'.__
if os.environ['TASK'] == 're-train':
    print("Re-train mode detected. Loading previous and current data to compute combined scale stats...")

    # Cargar estadísticas previas
    base_client = client.replace('_RETRAIN', '')
    base_path = f"/app/data/{base_client}"
    prev_scale_df = pd.read_csv(os.path.join(base_path, 'scale_params.csv'))

    expected_columns = prev_scale_df['sensor'].tolist()
    data_0 = data_0[expected_columns]

    # Cargar el csv original completo usado en el primer entrenamiento
    prev_data_path = os.path.join(base_path, 'data.csv')
    old_data = pd.read_csv(prev_data_path, low_memory=False)
    old_data.columns = expected_columns

    # Combinar ambos
    combined_data = pd.concat([old_data, data_0], axis=0)

    # Calcular nuevas métricas
    min_values = combined_data.min()
    max_values = combined_data.max()
    mean_values = combined_data.mean()
    median_values = combined_data.median()

    # Guardar nuevamente los archivos (opcional, si quieres sobreescribir)
    summary_df = pd.DataFrame({'sensor': expected_columns, 'min': min_values, 'max': max_values})
    summary_df.to_csv(output_dir + '/scale_params.csv', index=False)
    if "SAVE_FOLDER_PATH" in os.environ:
        summary_df.to_csv(f"{os.environ['SAVE_FOLDER_PATH']}/scale_params.csv", index=False)
    with open(output_dir + '/fix_values.json', 'w') as json_file:
        json.dump({col: {"0": val} for col, val in mean_values.items()}, json_file, indent=4)
    with open(output_dir + '/median_values.json', 'w') as json_file:
        json.dump({col: {"0": val} for col, val in median_values.items()}, json_file, indent=4)
else:
    print("Training from scratch. Generating new scale and imputation metrics...")
    # Escalado
    min_values = data_0.min()
    max_values = data_0.max()
    summary_df = pd.DataFrame({
        'sensor': data_0.columns,
        'min': min_values,
        'max': max_values
    })
    summary_df.to_csv(output_dir + '/scale_params.csv', index=False)
    if "SAVE_FOLDER_PATH" in os.environ:
        summary_df.to_csv(f"{os.environ['SAVE_FOLDER_PATH']}/scale_params.csv", index=False)
    print("File scale_params.csv created")

    # Media para imputación
    mean_values = data_0.mean()
    mean_dict = {column: {"0": value} for column, value in mean_values.items()}
    with open(output_dir + '/fix_values.json', 'w') as json_file:
        json.dump(mean_dict, json_file, indent=4)
    print("File fix_values.json created")

    # Mediana para diagnóstico u otros usos
    median_values = data_0.median()
    median_dict = {column: {"0": value} for column, value in median_values.items()}
    with open(output_dir + '/median_values.json', 'w') as json_file:
        json.dump(median_dict, json_file, indent=4)
    print("File median_values.json created")

# __MINMAX normalization__
X_data = data_0.iloc[:, :].to_numpy()

if os.environ['TASK'] == 're-train':
    print("Using combined statistics for MinMax normalization...")

    feature_range = (0, 1)
    range_vals = max_values.values - min_values.values
    zero_range_mask = range_vals == 0
    if np.any(zero_range_mask):
        print(f"Warning: Detected {np.sum(zero_range_mask)} constant columns with zero variance in combined data.")
        range_vals[zero_range_mask] = 1e-6

    scaler = MinMaxScaler(feature_range=feature_range)
    scaler.min_ = -min_values.values * (feature_range[1] - feature_range[0]) / range_vals
    scaler.scale_ = (feature_range[1] - feature_range[0]) / range_vals
    scaler.data_min_ = min_values.values
    scaler.data_max_ = max_values.values
    scaler.data_range_ = range_vals
    scaler.n_features_in_ = len(min_values)
    scaler.feature_names_in_ = np.array(expected_columns)
else:
    # Entrenamiento normal: ajusta el escalador con los datos actuales
    scaler = MinMaxScaler()
    scaler.fit(X_data)

normalized_data_X = scaler.transform(X_data)
normalized_data = pd.DataFrame(normalized_data_X, columns=data_0.columns)

# ## Downsample data
# if os.environ['TASK'] != 're-train':
#    filtered_data = normalized_data.groupby(np.arange(len(normalized_data))//10).median()
#    filtered_data = filtered_data.reset_index()
# else:
#    filtered_data = normalized_data.copy()
#normalized_data = normalized_data.iloc[:int(normalized_data.shape[0]*0.2)]

filtered_data = normalized_data.copy()

# __Split dataset to train and test.__
# index = int(filtered_data.shape[0] * 0.8)
# final_train = filtered_data.iloc[: index].copy()
# final_test = filtered_data.iloc[index :].copy()
final_train = filtered_data.copy()
final_test = filtered_data.copy()

# ## Generate Device list csv
column_names = normalized_data.columns.tolist()
df_devices = pd.DataFrame({
    'name': column_names,
    'type': f"{client} Device"
})
df_devices.to_csv(f"{output_dir}/DeviceImport.csv", index=False, header=True)
print("File DeviceImport.csv created")

labels = [0] * len(final_test)
with open(f"{output_dir}/anomaly_labels.txt", 'w') as f:
    f.write(','.join([str(i) for i in labels]))

# ## Data for GDN model
final_train.to_json(f"{output_dir}/train_{client.lower()}.json", indent=4, orient='columns')
final_test.to_json(f"{output_dir}/test_{client.lower()}.json", indent=4, orient='columns')
print("Csv files created")


# ## Generate Output Files
# __Import function for data generation__
def generate_graph_seq2seq_io_data(
        df, x_offsets, y_offsets, scaler=None):
    """
    Generate samples from
    :param df:
    :param x_offsets:
    :param y_offsets:
    :param add_time_in_day:
    :param add_day_in_week:
    :param scaler:
    :return:
    # x: (epoch_size, input_length, num_nodes, input_dim)
    # y: (epoch_size, output_length, num_nodes, output_dim)
    """
    if 'attack' in df.columns:
        df = df.drop(columns=['attack'])
    if 'timestamp' in df.columns:
        df = df.drop(columns=['timestamp'])

    num_samples, num_nodes = df.shape
    data = np.expand_dims(df.values, axis=-1)
    data_list = [data]
    data = np.concatenate(data_list, axis=-1)
    # epoch_len = num_samples + min(x_offsets) - max(y_offsets)
    x, y = [], []
    # t is the index of the last observation.
    min_t = abs(min(x_offsets))
    max_t = abs(num_samples - abs(max(y_offsets)))  # Exclusive
    for t in range(min_t, max_t):
        x_t = data[t + x_offsets, ...]
        y_t = data[t + y_offsets, ...]
        x.append(x_t)
        y.append(y_t)
    x = np.stack(x, axis=0)
    y = np.stack(y, axis=0)
    return x, y


def generate_train_val_test(df, test_size, val_ratio, window_size, output_dir):
    df = df.reset_index(drop=True)
    x_offsets = np.sort(
        np.concatenate((np.arange(-(window_size - 1), 1, 1),))
    )
    # Predict the next one hour
    y_offsets = np.sort(np.arange(1, 2, 1))
    # x: (num_samples, input_length, num_nodes, input_dim)
    # y: (num_samples, output_length, num_nodes, output_dim)
    x, y = generate_graph_seq2seq_io_data(
        df,
        x_offsets=x_offsets,
        y_offsets=y_offsets,
    )
    print("x shape: ", x.shape, ", y shape: ", y.shape)
    # Write the data into npz file.
    # num_test = 6831, using the last 6831 examples as testing.
    # for the rest: 7/8 is used for training, and 1/8 is used for validation.
    num_samples = x.shape[0]
    num_test = test_size
    train_samples = num_samples - num_test
    num_train = round(train_samples * (1 - val_ratio))
    num_val = train_samples - num_train
    # train
    x_train, y_train = x[:num_train], y[:num_train]
    # val
    x_val, y_val = (
        x[num_train: num_train + num_val],
        y[num_train: num_train + num_val],
    )
    # test
    x_test, y_test = (
        x[-num_test:],
        y[-num_test:],
    )
    for cat in ["train", "val", "test"]:
        _x, _y = locals()["x_" + cat], locals()["y_" + cat]
        print(cat, "x: ", _x.shape, "y:", _y.shape)
        np.savez_compressed(
            os.path.join(output_dir, "%s.npz" % cat),
            x=_x,
            y=_y,
            x_offsets=x_offsets.reshape(list(x_offsets.shape) + [1]),
            y_offsets=y_offsets.reshape(list(y_offsets.shape) + [1]),
        )


def generate_train_val_test_streaming(df, test_size, val_ratio, window_size, output_dir):
    """
    Genera datasets de entrenamiento, validación y test para modelos de predicción temporal
    a partir de datos multivariantes sensorizados, sin cargar todos los datos a memoria RAM.

    Utiliza `np.memmap` para almacenar los arrays intermedios directamente en disco
    y `np.savez_compressed` para guardar los datasets resultantes de forma comprimida.

    Parámetros:
    -----------
    df : pd.DataFrame
        DataFrame con las series temporales, con sensores como columnas.
    test_size : int
        Número de muestras a reservar para el conjunto de test.
    val_ratio : float
        Proporción del conjunto de entrenamiento que se usará como validación.
    window_size : int
        Número de pasos de entrada para cada muestra (ej. 80 → mirar 80 pasos previos).
    output_dir : str
        Ruta al directorio donde se guardarán los archivos generados.
    """

    df = df.reset_index(drop=True)
    x_offsets = np.sort(np.arange(-(window_size - 1), 1, 1))
    y_offsets = np.array([1])  # Predecir el siguiente paso

    # Elimina columnas innecesarias
    for col in ['attack', 'timestamp', 'index']:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Datos en forma (tiempo, sensores, 1)
    num_samples, num_nodes = df.shape
    data = np.expand_dims(df.values, axis=-1)

    total_sequences = num_samples - abs(min(x_offsets)) - max(y_offsets)
    print(f"Total sequences to generate: {total_sequences}")

    # Inicializar archivos temporales memmap
    x_shape = (total_sequences, len(x_offsets), num_nodes, 1)
    y_shape = (total_sequences, len(y_offsets), num_nodes, 1)

    x_path = os.path.join(output_dir, "x_memmap.npy")
    y_path = os.path.join(output_dir, "y_memmap.npy")

    x_memmap = np.memmap(x_path, dtype='float32', mode='w+', shape=x_shape)
    y_memmap = np.memmap(y_path, dtype='float32', mode='w+', shape=y_shape)

    # Construcción por streaming
    for i, t in enumerate(range(abs(min(x_offsets)), num_samples - max(y_offsets))):
        x_t = data[t + x_offsets, ...]
        y_t = data[t + y_offsets, ...]
        x_memmap[i] = x_t
        y_memmap[i] = y_t
        if i % 5000 == 0:
            print(f"Processed {i}/{total_sequences} sequences")

    # Divisiones de dataset
    num_test = test_size
    train_samples = total_sequences - num_test
    num_train = int(train_samples * (1 - val_ratio))
    num_val = train_samples - num_train

    splits = {
        "train": (0, num_train),
        "val": (num_train, num_train + num_val),
        "test": (total_sequences - num_test, total_sequences),
    }

    for name, (start_idx, end_idx) in splits.items():
        np.savez_compressed(
            os.path.join(output_dir, f"{name}.npz"),
            x=x_memmap[start_idx:end_idx],
            y=y_memmap[start_idx:end_idx],
            x_offsets=x_offsets.reshape([-1, 1]),
            y_offsets=y_offsets.reshape([-1, 1]),
        )
        print(f"{name}: x {x_memmap[start_idx:end_idx].shape}, y {y_memmap[start_idx:end_idx].shape}")

    # Limpieza
    del x_memmap, y_memmap
    os.remove(x_path)
    os.remove(y_path)


# __Data Generate__
data = pd.concat([final_train, final_test]).reset_index(drop=True)
if "index" in data.columns:
    data = data.drop(columns="index")
else:
    pass
val_ratio = 0.2
window_size = 12
#generate_train_val_test(data, len(final_test), val_ratio, window_size, output_dir)
generate_train_val_test_streaming(data, len(final_test), val_ratio, window_size, output_dir)
