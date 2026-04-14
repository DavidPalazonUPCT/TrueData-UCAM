# Parámetros Iniciales
ROOT_Thingsboard = "http://172.25.0.2:9090"
LOCAL_Thingsboard = "http://localhost:9090"

#Cargamos las librerías necesarias
import requests
import pandas as pd
import json

## Cargamos datos del cliente
Parametros_cliente_json = open("deploy/Client.json")
Parametros_cliente = json.load(Parametros_cliente_json)
Parametros_cliente_json.close()
Customer = Parametros_cliente["Client"]
# Parámetros de Consulta
ficherodatos = f"deploy/{Customer}/Niveles de Criticidad.csv"

# Leemos fichero con dispositivos Core
df_buckets_core = pd.read_csv(f"deploy/{Customer}/DeviceimportCredentials_CORE.csv")

accessToken = df_buckets_core["accessToken"][df_buckets_core["name"]=="CLIENTES Niveles de Criticidad"]

### INCLUIR ENDOPOINT ASOCIADO AL BUCKET NIVELES DE CRITICIDAD
endpoint = f'{LOCAL_Thingsboard}/api/v1/{accessToken[0]}/telemetry'

data = pd.read_csv(ficherodatos, delimiter=";")
datos = data.to_json(orient="records")

# Función que sube datos a un endpoint
def post_data(data,endpoint):
    headers = {"Content-Type":"application/json;charset=UTF-8", "Accept":"application/json"}
    try:
        response = requests.post(endpoint, headers=headers, data=data)
    except Error as err:
        print('La página no existe. Codigo: '+str(err.code))
        print(err.headers)
        print(err.reason)
        return None
    return response


for i in range(data.shape[0]):
    datos = data.iloc[i].to_json()
    response = post_data(datos, endpoint)
    print(response)
