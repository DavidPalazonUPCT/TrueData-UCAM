## -*- coding: cp1252 -*-
__author__ = 'apl'
## Extracci?n Agregados
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

# Parametros de Consulta (pueden ser par?metros o argumentos de entrada)
model_list = {"stgnn-gat", "cognn"}
model_used = os.getenv("MODEL")
if model_used not in model_list:
    raise ValueError(f"Modelo no válido para MODEL: {model_used}. Los modelos permitidos son: {model_list}")
os.environ['MODEL_NAME'] = os.environ['MODEL'].split('-')[0].upper()
# Elección de modelo
if os.environ['CLIENT'] == 'WADI':
    if os.environ['MODEL_NAME'] == 'STGNN':
        Modelo = "WADI Model M2"
        EST = "WADI Estimaciones M2"
        EST_rel = "WADI Estimaciones relativo M2"
    elif os.environ['MODEL_NAME'] == 'COGNN':
        Modelo = "WADI Model M3"
        EST = "WADI Estimaciones M3"
        EST_rel = "WADI Estimaciones relativo M3"
elif os.environ['CLIENT'] == 'SWAT':
    if os.environ['MODEL_NAME'] == 'STGNN':
        Modelo = "SWAT Model M2"
        EST = "SWAT Estimaciones M2"
        EST_rel = "SWAT Estimaciones relativo M2"
    elif os.environ['MODEL_NAME'] == 'COGNN':
        Modelo = "SWAT Model M3"
        EST = "SWAT Estimaciones M3"
        EST_rel = "SWAT Estimaciones relativo M3"
elif os.environ['CLIENT'] == 'MCT':
    if os.environ['MODEL_NAME'] == 'STGNN':
        Modelo = "MCT Model M2"
        EST = "MCT Estimaciones M2"
        EST_rel = "MCT Estimaciones relativo M2"
    elif os.environ['MODEL_NAME'] == 'COGNN':
        Modelo = "MCT Model M3"
        EST = "MCT Estimaciones M3"
        EST_rel = "MCT Estimaciones relativo M3"
elif os.environ['CLIENT'] == 'ESAMUR':
    if os.environ['MODEL_NAME'] == 'STGNN':
        Modelo = "ESAMUR Model M2"
        EST = "ESAMUR Estimaciones M2"
        EST_rel = "ESAMUR Estimaciones relativo M2"
    elif os.environ['MODEL_NAME'] == 'COGNN':
        Modelo = "ESAMUR Model M3"
        EST = "ESAMUR Estimaciones M3"
        EST_rel = "ESAMUR Estimaciones relativo M3"
else:
    raise ValueError(f"El modelo {model_used} no se encuentra en 'Repomodelos'.")
print("Modelo:     {}".format(Modelo))
print("Estimación: {}".format(EST))
print("Estimación relativa: {}".format(EST_rel))
ficherodatos = "src/dataloader/ETL/out.json" # en formato JSON
ficheroabs = "src/dataloader/ETL/abs_error.json" # en formato JSON
ficherorel = "src/dataloader/ETL/rel_error.json" # en formato JSON

# Repositorio de informacion agregada
with open(f'src/dataloader/Credenciales.txt') as file:
    credenciales = file.read().strip()
tok, _ = extract_token(credenciales)
os.environ['TOKEN'] = f"Bearer {tok}"
## Obtener los IDs de los buckets
model_id = extract_id(Modelo)
est_id = extract_id(EST)
est_rel_id = extract_id(EST_rel)
## Obtener los accesstoken de los buckets
model_token = extract_Credentials(model_id)
est_token = extract_Credentials(est_id)
est_rel_token = extract_Credentials(est_rel_id)
endpoint_model = f"{os.environ['ROOT']}/api/v1/{model_token}/telemetry"
endpoint_est = f"{os.environ['ROOT']}/api/v1/{est_token}/telemetry"
endpoint_est_rel = f"{os.environ['ROOT']}/api/v1/{est_rel_token}/telemetry"
print("endpoint_model: {}".format(endpoint_model))
print("endpoint_est: {}".format(endpoint_est))
print("endpoint_est_rel: {}".format(endpoint_est_rel))

# Lectura del fichero de datos
f_out = open(ficherodatos, "r")
f_abs = open(ficheroabs, "r")
f_rel = open(ficherorel, "r")
datos = f_out.read()
abs_error = f_abs.read()
rel_error = f_rel.read()
#print("Respuesta del modelo: ")
#print(datos)
#print("Diferencia (Abs): ")
#print(abs_error)

# Funci?n que devuelve el token y el refresh token de ThingsBoard
def post_data(data,endpoint):
    headers = {"Content-Type":"application/json;charset=UTF-8", "Accept":"application/json"}
    try:
        response = requests.post(endpoint, headers=headers, data=data)
    except requests.exceptions.RequestException as err:
        print('La pagina no existe. Codigo: '+str(err.code))
        #print(err.headers)
        print(err.reason)
        return None
    return response

response_out = post_data(datos,endpoint_model)
response_pred = post_data(abs_error,endpoint_est)
response_pred_rel = post_data(rel_error,endpoint_est_rel)
print(response_out)