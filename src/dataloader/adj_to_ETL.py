## -*- coding: cp1252 -*-
__author__ = 'apl'
## Extracción Agregados
## Fecha: 06/05/2024
## Licencia Creative Commons
##
##
## Paquetes Externos Necesarios
import requests
import pandas as pd
import json
import re
import os
from sensorsloader import extract_token

def extract_id(deviceName):
    endpoint = f"{os.environ['ROOT']}/api/tenant/devices?deviceName={str(deviceName)}"
    headers = {"Authorization": os.environ['TOKEN'],"Content-Type":"application/json;charset=UTF-8", "Accept":"application/json"}
    try:
        response = requests.get(endpoint, headers=headers).json()
        #print(response)
    except Error as err:
        print('La página no existe. Codigo: '+str(err.code))
        print(err.headers)
        print(err.reason)
        #sys.exit()
        return None
    return response['id']['id']

def extract_Credentials(deviceId):
    endpoint = f"{os.environ['ROOT']}/api/device/{deviceId}/credentials"
    headers = {"Authorization": os.environ['TOKEN'],"Content-Type":"application/json;charset=UTF-8", "Accept":"application/json"}
    try:
        response = requests.get(endpoint, headers=headers)
        if response.status_code == 200:
            return response.json().get('credentialsId')
        else:
            print(f"Error: HTTP {response.status_code} - {response.reason}")
            return None
    except requests.RequestException as err:
        print('Error al conectar con el servidor. Detalles del error:', err)
        return None

# Comando
# MODEL='cognn' CLIENT='SWAT' python3 src/dataloader/adj_to_ETL.py

# Parámetros de Consulta (pueden ser parámetros o argumentos de entrada)
model_list = {"stgnn-gat", "cognn"}
model_used = os.getenv("MODEL")
if model_used not in model_list:
    raise ValueError(f"Modelo no válido para MODEL: {model_used}. Los modelos permitidos son: {model_list}")
os.environ['MODEL_NAME'] = os.environ['MODEL'].split('-')[0].upper()
if os.environ['CLIENT'] == 'WADI':
    if os.environ['MODEL_NAME'] == 'STGNN':
        ADJ_name = "WADI Matriz Model M2"
    elif os.environ['MODEL_NAME'] == 'COGNN':
        ADJ_name = "WADI Matriz Model M3"
elif os.environ['CLIENT'] == 'SWAT':
    if os.environ['MODEL_NAME'] == 'STGNN':
        ADJ_name = "SWAT Matriz Model M2"
    elif os.environ['MODEL_NAME'] == 'COGNN':
        ADJ_name = "SWAT Matriz Model M3"
path = 'src'
if not os.path.isdir(path):
    path = '/app'
else:
    pass
with open(f'./src/dataloader/Credenciales.txt') as file:
    credenciales = file.read().strip()
tok, _ = extract_token(credenciales)
os.environ['TOKEN'] = f"Bearer {tok}"
## Obtener los IDs de los buckets
adj_id = extract_id(ADJ_name)
## Obtener los accesstoken de los buckets
adj_token = extract_Credentials(adj_id)
ficherodatos = f"{path}/models/{os.environ['CLIENT']}/{os.environ['MODEL_NAME']}/adj.json"  # en formato JSON
endpoint_adj = f"{os.environ['ROOT']}/api/v1/{adj_token}/telemetry"
print(endpoint_adj)

# Lectura del fichero de datos
f = open(ficherodatos, "r")
datos = f.read()
#print(datos)


# Función que devuelve el token y el refresh token de ThingsBoard
def post_data(data,endpoint):
    headers = {"Content-Type":"application/json;charset=UTF-8", "Accept":"application/json"}
    try:
        response = requests.post(endpoint, headers=headers, data=data)
    except requests.exceptions.RequestException as err:
        print('La página no existe. Codigo: '+str(err.code))
        #print(err.headers)
        print(err.reason)
        return None
    return response

response = post_data(datos,endpoint_adj)
print(response)