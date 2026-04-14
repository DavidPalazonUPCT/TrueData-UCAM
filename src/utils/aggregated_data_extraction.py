## -*- coding: cp1252 -*-
__author__ = 'apl'
## Extracción Agregados
## Fecha: 06/05/2024
## Licencia Creative Commons
##
##
## Paquetes Externos Necesarios
import argparse
import requests
import pandas as pd
import numpy as np

# Constants
ENDPOINT_LOGIN = "http://portal.airtrace.io:8080/api/auth/login"
ENDPOINT_TELEMETRY_KEYS = "http://portal.airtrace.io:8080/api/plugins/telemetry/{}/{}" \
                          "/keys/timeseries"
ENDPOINT_TELEMETRY_VALUES = "http://portal.airtrace.io:8080/api/plugins/telemetry/{}/{}" \
                            "/values/timeseries"

# Read Credentials
def read_credentials(file_path):
    with open(file_path) as fichero:
        credenciales = fichero.read()
    return credenciales

# Function that returns the token and the refresh token from ThingsBoard
def extract_token(credenciales):
    headers = {"Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    try:
        response = requests.post(ENDPOINT_LOGIN, headers=headers, data=credenciales).json()
        return response['token'], response['refreshToken']
    except requests.RequestException as err:
        print(f'Error connecting to the server: {err}')
        return None, None

# Function that returns the variables (keys) from a ThingsBoard repository
def extract_keys(deviceType, deviceID, token):
    endpoint = ENDPOINT_TELEMETRY_KEYS.format(deviceType, deviceID)
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    try:
        response = requests.get(endpoint, headers=headers).json()
        return response
    except requests.RequestException as err:
        print(f'Error connecting to the server: {err}')
        return []

# Function to extract telemetry from ThingsBoard
def extract_telemetry(N, deviceType, deviceID, keys, token):
    params = {
        "keys": keys,
        "startTs": 1000000000000,
        "endTs": 9999999999999,
        "limit": N,
        "orderBy": "DESC"
    }
    endpoint = ENDPOINT_TELEMETRY_VALUES.format(deviceType, deviceID)
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    try:
        response = requests.get(endpoint, headers=headers, params=params).json()
        return response
    except requests.RequestException as err:
        print(f'Error connecting to the server: {err}')
        return {}

# Process to transform telemetry data
def transform_telemetry_data(datos):
    return {key: {x['ts']: x["value"] for x in datos[key]} for key in datos.keys()}

# Process to create DataFrame from data
def create_dataframe_from_telemetry(datosTrans):
    return pd.DataFrame.from_dict(datosTrans, orient="columns")

# Save DataFrames to CSV
def save_dataframes(df, dfNaN, path='datos.csv', pathNaN='datosNaN.csv'):
    df.to_csv(path, index=False)
    dfNaN.to_csv(pathNaN, index=False)

def main():
    # Setup argparse
    parser = argparse.ArgumentParser(description='Telemetry Data Extraction and Processing')
    parser.add_argument('--n', type=int, default=20, help='Number of past windows to extract')
    parser.add_argument('--nulo', type=str, default="None", help='Value to fill empty/null values')
    parser.add_argument('--metodo', type=str, default="MEDIANA10", help='Method to use (MEDIANA10, MEDIANA5, MEDIA10, MEDIA5)')
    parser.add_argument('--credentials', type=str, default='credenciales.txt', help='File path for credentials')
    parser.add_argument('--devices', type=str, default='DeviceImport.csv', help='File path for device import')
    parser.add_argument('--repos', type=str, default='Repositorios.csv', help='File path for repositories')
    parser.add_argument('--output', type=str, default='./aggregation_files/datos.csv', help='Path for output files (normal)')
    parser.add_argument('--outputNan', type=str, default='./aggregation_files/datosNan.csv', help='Path for output files (nans)')

    args = parser.parse_args()

    # Load parameters from argparse
    N = args.n
    Nulo = args.nulo
    Metodo = args.metodo
    output = args.output
    outputNan = args.outputNan

    # Load credentials
    credenciales = read_credentials(args.credentials)
    print(credenciales)

    # Extract Tokens
    tok, refreshTok = extract_token(credenciales)
    if tok is None:
        print("Failed to extract tokens. Check your credentials and network connection.")
        return
    TOKEN = "Bearer " + str(tok)
    #print(TOKEN)

    # Load device list
    dispositivos = pd.read_csv(args.devices)
    ListaDispositivos = dispositivos['name'].array
    ListaDispositivos = ListaDispositivos.insert(0, 'timestamp')
    print(ListaDispositivos)

    # Repository of aggregated information
    dfRepos = pd.read_csv(args.repos)
    deviceID = dfRepos.loc[dfRepos['NombreRepo'] == Metodo, 'deviceID'][0]
    deviceType = dfRepos.loc[dfRepos['NombreRepo'] == Metodo, 'deviceType'][0]
    print(deviceID)
    print(deviceType)

    # Extract available variables
    keysList = extract_keys(deviceType, deviceID, tok)
    print("keyList: ")
    print(keysList)

    # Convert keys list to comma-separated string
    keysString = ','.join(keysList)
    print("KeyString: ")
    print(keysString)

    # Extract Telemetry
    datos = extract_telemetry(N, deviceType, deviceID, keysString, tok)
    print("telemetria: ")
    print(datos)

    # Transform Telemetry Data
    datosTrans = transform_telemetry_data(datos)
    print("Datos Trans ")
    print(datosTrans)

    # Create DataFrame from Transformed Data
    df_datos = create_dataframe_from_telemetry(datosTrans)
    print("DataFrame ")
    print(df_datos)

    # Process to select the N most recent records
    Nrows = len(df_datos)
    if Nrows > N:
        pos = range(N, Nrows)
        df_datos.reset_index(drop=True, inplace=True)
        df_datos.drop(df_datos.index[pos], inplace=True)
    print(df_datos)

    # Replace NULO with np.nan before saving
    newdf_datos = df_datos.replace(Nulo, np.nan)
    print(newdf_datos)

    # Save DataFrames to Files
    save_dataframes(df_datos, newdf_datos, output, outputNan)

if __name__ == "__main__":
    main()
