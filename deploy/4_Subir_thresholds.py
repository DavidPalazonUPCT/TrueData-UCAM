import json
import pandas as pd
import APIThingsboard
import os
import requests


def extract_token(credenciales):
    print(f"ROOT: {os.environ['ROOT']}")
    endpoint = f"{os.environ['ROOT']}/api/auth/login"
    headers = {"Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    data = json.dumps(credenciales)
    print(data)
    response = requests.post(endpoint, headers=headers, data=data).json()
    return response['token'], response['refreshToken']


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


# ========= CONFIGURACIÓN =========
os.environ['ROOT'] = "http://localhost:9090"
## Cargamos datos del cliente
Parametros_cliente_json = open("deploy/Client.json")
Parametros_cliente = json.load(Parametros_cliente_json)
Parametros_cliente_json.close()
client = Parametros_cliente["Client"]
model = Parametros_cliente["Model"]
if model == "M1":
    model_name = "GDN"
elif model == "M2":
    model_name = "STGNN"
elif model == "M3":
    model_name = "COGNN"
else:
    raise "Error modelo no disponible."

csv_path = f"src/models/{client}/{model_name}/score_max.csv"
device_name = f"{client} {model} Thresholds"
device_profile = f"{model} {client} Thresholds"


# ========= CREDENCIALES & TOKEN =========
#with open(f'src/dataloader/Credenciales.txt') as file:
#    credenciales = file.read().strip()

fichero = open('deploy/ParametrosConfiguracion.txt')

ParametrosConfiguracion = fichero.read()

# Cerramos el archivo para liberar recursos.
fichero.close()

# Convertimos la cadena de texto JSON leída del archivo en un diccionario de Python para un acceso más fácil a los parámetros.
Parametros = json.loads(ParametrosConfiguracion)

## Extraemos las credenciales de Tenant de los parámetros de configuración cargados previamente.
# Las credenciales del Tenant se utilizan para autenticarse y realizar operaciones en la plataforma ThingsBoard bajo el contexto de este Tenant.
credenciales_tb = Parametros["CredencialesTenantThings"]

tok, _ = extract_token(credenciales_tb)
os.environ['TOKEN'] = f"Bearer {tok}"
print(f"token: {os.environ['TOKEN']}")
APIThingsboard.Root = "http://localhost:9090"
APIThingsboard.TOKEN = os.environ['TOKEN']

# ========= ID del Cliente =========
#CustomerId, status = APIThingsboard.clienteIDStatus(client)
#APIThingsboard.CustomerId = CustomerId

# ========= CREAR / VERIFICAR DEVICE =========
device_id = APIThingsboard.crear_device(device_name, device_profile)

print(f"✅ Device '{device_name}' creado o verificado con ID: {device_id}")

# ========= CARGAR DATOS DEL CSV =========
df = pd.read_csv(csv_path)
# Convertir a diccionario {sensor_name: score_max}
thresholds_data = dict(zip(df["name"], df["score_max"]))
thresholds_data_json = json.dumps([thresholds_data])
#print(f"thresholds_data type: {type(thresholds_data)}")
#print(f"thresholds_data: {thresholds_data}")

# ========= SUBIR ATRIBUTOS AL DEVICE =========
device_thresholds_id = extract_id(device_name)
device_thresholds_token = extract_Credentials(device_thresholds_id)
endpoint_thresholds = f"{os.environ['ROOT']}/api/v1/{device_thresholds_token}/telemetry"
#print("endpoint_thresholds: {}".format(endpoint_thresholds))

response_out = post_data(thresholds_data_json, endpoint_thresholds)

print(f"✅ Thresholds subidos a '{device_name}': {len(thresholds_data)} entradas")
