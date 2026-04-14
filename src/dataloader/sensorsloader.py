import requests
import pandas as pd
import numpy as np
import os
import json

def load_credentials():
    with open('/app/dataloader/Credenciales.txt') as file:
        credenciales = file.read().strip()
    print(credenciales)
    return credenciales


def load_device_repository(metodo):
    dfRepos = pd.read_csv('/app/dataloader/CLIENT/Repositorios.csv')
    deviceType = "DEVICE"
    deviceID = dfRepos.loc[(dfRepos['NombreRepo'] == metodo) & (dfRepos['cliente'] == os.environ['CLIENT']), 'deviceID'].values[0]
    return deviceID, deviceType


def extract_token(credenciales):
    #http://portal.airtrace.io:8080
    print(f"ROOT: {os.environ['ROOT']}")
    endpoint = f"{os.environ['ROOT']}/api/auth/login"
    headers = {"Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    response = requests.post(endpoint, headers=headers, data=credenciales).json()
    return response['token'], response['refreshToken']

def extract_id(deviceName, TOKEN):
    endpoint = f"{os.environ['ROOT']}/api/tenant/devices?deviceName={str(deviceName)}"
    headers = {"Authorization": TOKEN, "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    print(f"endpoint: {endpoint}")
    print(f"headers: {headers}")
    try:
        response = requests.get(endpoint, headers=headers).json()
    except Exception as err:
        print('La página no existe. Codigo: ' + str(err.code))
        print(err.headers)
        print(err.reason)
        # sys.exit()
        return None
    return response['id']['id']


def extract_keys(deviceType, deviceID, TOKEN):
    endpoint = f"{os.environ['ROOT']}/api/plugins/telemetry/{deviceType}/{deviceID}/keys/timeseries"
    headers = {"Authorization": TOKEN, "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    #print("endpoint_key: {}".format(endpoint))
    #print("headers_key: {}".format(headers))
    response = requests.get(endpoint, headers=headers).json()
    #print("response_key: {}".format(response))
    return response


def extract_telemetry(N, deviceType, deviceID, keys, TOKEN):
    print("=== Extracting telemetry ===")
    params = {
        "keys": keys,
        "startTs": 1000000000000,
        "endTs": 9999999999999,
        "limit": N,
        "orderBy": "DESC"
    }
    endpoint = f"{os.environ['ROOT']}/api/plugins/telemetry/{deviceType}/{deviceID}/values/timeseries"
    headers = {"Authorization": TOKEN, "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    print("endpoint: {}".format(endpoint))
    #print("headers: {}".format(headers))
    response = requests.get(endpoint, headers=headers, params=params).json()
    #print("Response")
    #print("response: {}".format(type(response)))
    #print("")
    return response

def manage_null_data(df, save_file=f"/app/data/{os.environ['CLIENT']}/fix_values.json"):
    print("=== Fixing null values in data ===")
    if os.path.exists(save_file):
        # Load mean values from the file
        mean_df_0 = pd.read_json(save_file, orient='columns')
        df_0 = df.copy()
        df_0 = df_0.drop(columns='timestamp')
        os.environ['NUM_NODES'] = str(mean_df_0.shape[1])
        print('Number of sensors: {}'.format(os.environ['NUM_NODES']))
        mean_df = mean_df_0[df_0.columns].copy()
        # Replace NaN or null values with the mean of each column
        df_fix = df_0.copy()
        #print("Tipos de datos de las columnas:")
        # Convertir columnas de str a int (manejo de NaN y valores no numéricos)
        for col in df_fix.columns:
            df_fix[col] = pd.to_numeric(df_fix[col], errors='coerce')

        empty_cols = [col for col in df_fix.columns if df_fix[col].isnull().all()]
        df_fix[empty_cols] = df_fix[empty_cols].fillna(mean_df[empty_cols])
        none_string_cols = [col for col in df_fix.columns if (df_fix[col] == "None").all()]  # None string
        for col in none_string_cols:
            df_fix[col] = df_fix[col].replace("None", mean_df[col].values[0])
        nan_cols = [col for col in df_fix.columns if df_fix[col].isna().all()]  # Nan
        for col in nan_cols:
            df_fix[col] = df_fix[col].fillna(mean_df[col].values[0])
        for i in df_fix.columns[df_fix.isnull().any(axis=0)]:      # ---Applying Only on variables with null values
            df_fix[i] = df_fix[i].fillna(df_fix[i])
        for i in df_fix.columns[(df_fix == "None").any(axis=0)]:   # ---Applying Only on variables with "None" values
            df_fix[i] = df_fix[i].replace("None", np.nan)
            df_fix[i] = df_fix[i] = df_fix[i].apply(pd.to_numeric, errors='coerce')
            mean_value = df_fix[i].median()                        # ---Median is more stable than the mean
            df_fix[i] = df_fix[i].fillna(df_fix[i].mean_value)
        for i in df_fix.columns[df_fix.isna().any(axis=0)]:        # ---Applying Only on variables with NaN values
            df_fix[i] = df_fix[i].fillna(df_fix[i].median()).infer_objects()
        # Save mean values
        mean_values_new = df_fix.median()
        mean_dict_new = mean_values_new.to_dict()
        # Save the mean values to a JSON file
        mean_df_new = pd.DataFrame([mean_dict_new])
        mean_df_0.update(mean_df_new)
        mean_df_0.to_json(save_file, orient='columns', indent=4)
    else:
        df_fix = df.copy()
        empty_cols = [col for col in df_fix.columns if df_fix[col].isnull().all()]          # Nulls
        df_fix[empty_cols] = df_fix[empty_cols].fillna(0)
        none_string_cols = [col for col in df_fix.columns if (df_fix[col] == "None").all()] # None string
        df_fix[none_string_cols] = df_fix[none_string_cols].replace("None", 0)
        nan_cols = [col for col in df_fix.columns if df_fix[col].isna().all()]              # Nan
        df_fix[nan_cols] = df_fix[nan_cols].fillna(0)
        for i in df_fix.columns[df_fix.isnull().any(axis=0)]:     # ---Applying Only on variables with null values
            df_fix[i] = df_fix[i].fillna(df_fix[i].median())
        for i in df_fix.columns[(df_fix == "None").any(axis=0)]:  # ---Applying Only on variables with "None" values
            df_fix[i] = df_fix[i].replace("None", np.nan, inplace=True)
            df_fix[i] = df_fix[i].apply(pd.to_numeric, errors='coerce')
            mean_value = df_fix[i].median()
            df_fix[i] = df_fix[i].fillna(mean_value)
        for i in df_fix.columns[df_fix.isna().any(axis=0)]:       # ---Applying Only on variables with NaN values
            df_fix[i] = df_fix[i].fillna(df_fix[i].median())
        # Save mean values
        mean_values = df_fix.median()
        mean_dict = mean_values.to_dict()
        # Save the mean values to a JSON file
        mean_df = pd.DataFrame([mean_dict])
        mean_df.to_json(save_file, orient='columns', indent=4)
    print("Fixed dataset")
    df.update(df_fix)

    return df

def get_sensordata(N, Nulo, Metodo):
    print(f"seq_in_len: {N}, rows fetched (N+1): {N+1}")
    print(f"Parámetro Nulo: {Nulo}")
    print(f"Parámetro Metodo: {Metodo}")
    # Load credentials
    credenciales = load_credentials()
    print(f"Credenciales: {credenciales}")
    # Extract token
    tok, _ = extract_token(credenciales)
    TOKEN = f"Bearer {tok}"
    #print(f"TOKEN: {TOKEN}")

    # Load device repository information
    print("=== Loading configuration ETL ===")
    #deviceID, deviceType = load_device_repository(Metodo)
    if "_RETRAIN" in os.environ['CLIENT']:
        os.environ['CLIENT'] = os.environ['CLIENT'].split('_')[0]
    if Metodo == "MEDIANA1":
        Metodo = f"{os.environ['CLIENT']} Aggregation Mediana Ventana 1seg"
    elif Metodo == "MEDIANA5":
        Metodo = f"{os.environ['CLIENT']} Aggregation Mediana Ventana 5seg"
    elif Metodo == "MEDIANA10":
        Metodo = f"{os.environ['CLIENT']} Aggregation Mediana Ventana 10seg"
    elif Metodo == "MEDIA1":
        Metodo = f"{os.environ['CLIENT']} Aggregation Media Ventana 1seg"
    elif Metodo == "MEDIA5":
        Metodo = f"{os.environ['CLIENT']} Aggregation Media Ventana 5seg"
    elif Metodo == "MEDIA10":
        Metodo = f"{os.environ['CLIENT']} Aggregation Media Ventana 10seg"
    deviceID = extract_id(Metodo, TOKEN)
    deviceType = "DEVICE"
    print("deviceID:   {}".format(deviceID))
    print("deviceType: {}".format(deviceType))

    # Extract available keys
    keysList = extract_keys(deviceType, deviceID, TOKEN)
    keysString = ','.join(keysList)

    # Extract telemetry data
    datos = extract_telemetry(N, deviceType, deviceID, keysString, TOKEN)
    #print(datos.keys())
    #print(datos)

    # Transform telemetry data
    datosTrans = {key: {x['ts']: x["value"] for x in datos[key]} for key in datos.keys()}

    #### Test de nulos  ####
    #with open('/app/dataloader/ETL/TEST/MCT/datos.json', 'r') as file:
    #    datosTrans = json.load(file)
    ####                ####

    # Create DataFrame
    df_datos = pd.DataFrame.from_dict(datosTrans, orient="columns")
    if os.environ["TASK"] != "re-train":
        df_datos = df_datos.iloc[0:N].copy()
    print("=== Data from ETL loaded ===")
    print("Data shape:")
    print("Number of rows: {}".format(df_datos.shape[0]))
    print("Number of sensors: {}".format(df_datos.shape[1]))
    if os.environ["TASK"] != "re-train":
        df_datos.to_csv('/app/dataloader/ETL/datos.csv', index=False)

        # Replace null values with np.nan
        newdf_datos = manage_null_data(df=df_datos)
        # Transformar el DataFrame limpio a JSON
        datos_trans_final = newdf_datos.to_dict()

        #### Test de nulos  ####
        #with open('/app/dataloader/ETL/TEST/MCT/datos.json', 'w') as file:
        #    json.dump(datos_trans_final, file, indent=4)
        newdf_datos = df_datos.replace(Nulo, np.nan)
        ####                 ####

        #print(newdf_datos)

        # Save DataFrame as CSV
        newdf_datos.to_csv('/app/dataloader/ETL/datosNaN.csv', index=False)

        return datos_trans_final

    else:
        os.environ['CLIENT'] = os.environ['CLIENT'] + "_RETRAIN"
        # Create folder
        os.makedirs(os.path.dirname(f"/app/data/{os.environ['CLIENT']}"), exist_ok=True)
        # Save DataFrame as CSV
        df_datos.to_csv(f"/app/data/{os.environ['CLIENT']}/data.csv", index=False)
        return "ok"