# Parámetros Iniciales
# ROOT
ROOT_Thingsboard = "http://172.25.0.2:9090"
ROOT_NodeRed = "http://172.25.0.3:1880"
LOCAL_Thingsboard = "http://localhost:9090"
LOCAL_NodeRed = "http://localhost:1880"

# Cargamos las librerías necesarias
import requests
from requests.auth import HTTPBasicAuth
import pandas as pd
import json
import APIThingsboard


## Cargamos datos del cliente
Parametros_cliente_json = open("deploy/Client.json")
Parametros_cliente = json.load(Parametros_cliente_json)
Parametros_cliente_json.close()
Customer = Parametros_cliente["Client"]

## Cargamos los dispositivos auxiliares desde un archivo CSV específico del cliente.
# Este archivo contiene las credenciales de acceso de los dispositivos creados previamente.
OtherDevices = pd.read_csv(f'deploy/{Customer}/OthersimportCredentials_{Customer}.csv')

# Extraemos los tokens de acceso para los dispositivos de agregación con diferentes configuraciones.
# Estos tokens se utilizarán para autenticar las solicitudes de API en Node-RED.
# Token de acceso para el dispositivo de agregación de Media con ventana de 1 segundos.
IDMEDIA1ID = \
OtherDevices.loc[OtherDevices["name"] == f'{Customer} Aggregation Media Ventana 1seg', "accessToken"].iloc[0]
# Token de acceso para el dispositivo de agregación de Media con ventana de 5 segundos.
IDMEDIA5ID = \
OtherDevices.loc[OtherDevices["name"] == f'{Customer} Aggregation Media Ventana 5seg', "accessToken"].iloc[0]
# Token de acceso para el dispositivo de agregación de Media con ventana de 10 segundos.
IDMEDIA10ID = \
OtherDevices.loc[OtherDevices["name"] == f'{Customer} Aggregation Media Ventana 10seg', "accessToken"].iloc[0]
# Token de acceso para el dispositivo de agregación de Mediana con ventana de 1 segundos.
IDMEDIANA1ID = \
OtherDevices.loc[OtherDevices["name"] == f'{Customer} Aggregation Mediana Ventana 1seg', "accessToken"].iloc[0]
# Token de acceso para el dispositivo de agregación de Mediana con ventana de 5 segundos.
IDMEDIANA5ID = \
OtherDevices.loc[OtherDevices["name"] == f'{Customer} Aggregation Mediana Ventana 5seg', "accessToken"].iloc[0]
# Token de acceso para el dispositivo de agregación de Mediana con ventana de 10 segundos.
IDMEDIANA10ID = \
OtherDevices.loc[OtherDevices["name"] == f'{Customer} Aggregation Mediana Ventana 10seg', "accessToken"].iloc[0]

## Cargamos los parámetros de configuración desde un archivo de texto.
# Abrimos el archivo 'ParametrosConfiguracion.txt' que contiene las configuraciones en formato JSON.
fichero = open('deploy/ParametrosConfiguracion.txt')

# Leemos el contenido completo del archivo y lo almacenamos en una variable.
ParametrosConfiguracion = fichero.read()

# Cerramos el archivo para liberar recursos.
fichero.close()

# Convertimos la cadena de texto JSON leída del archivo en un diccionario de Python para un acceso más fácil a los parámetros.
Parametros = json.loads(ParametrosConfiguracion)

# Extraemos las credenciales específicas para Node-RED de los parámetros de configuración cargados previamente.
# Las credenciales de Node-RED se utilizan para autenticarse y realizar operaciones en Node-RED.
credenciales_nd = Parametros["CredencialesNodeRed"]
credenciales_tb = Parametros["CredencialesTenantThings"]

TB_USER = credenciales_tb["username"]
TB_PASS = credenciales_tb["password"]


## Función que devuelve el token y el refresh token de Node-RED
def extract_token_nodered(credenciales):
    """
    Esta función obtiene el token de acceso y el token de actualización para Node-RED utilizando las credenciales proporcionadas.

    Args:
    credenciales (dict): Un diccionario que contiene las credenciales necesarias para autenticarse en Node-RED.

    Returns:
    tuple: Una tupla que contiene el token de acceso y el tiempo de expiración del token en segundos.
           Retorna None si ocurre un error durante la solicitud.

    Ejemplo de uso:
    >>> credenciales = {
            "username": "tu_usuario",
            "password": "tu_contraseña"
        }
    >>> access_token, expires_in = extract_token_nodered(credenciales)
    >>> print(access_token, expires_in)
    """
    # Agregamos los campos necesarios a las credenciales
    credenciales["client_id"] = "node-red-admin"
    credenciales["grant_type"] = "password"
    credenciales["scope"] = "*"

    # Endpoint de autenticación de Node-RED
    endpoint = f"{LOCAL_NodeRed}/auth/token"
    print(endpoint)
    # Convertimos las credenciales a formato JSON
    data = json.dumps(credenciales)
    print(data)

    # Configuramos los headers para la solicitud HTTP
    headers = {"Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}

    try:
        # Realizamos la solicitud POST para obtener el token
        response = requests.post(endpoint, headers=headers, data=data)
        # print(response)
    except requests.RequestException as err:
        # Manejamos errores relacionados con la solicitud HTTP
        print('Error al conectar con el servidor. Detalles del error:', err)
        return None

    # Devolvemos el token de acceso y el tiempo de expiración
    token_data = response.json()
    return token_data.get('access_token')


## Función que crea un flujo en Node-RED
def crear_flow_nodered(flow, credenciales, token='token'):
    """
    Esta función crea un flujo en Node-RED utilizando los datos proporcionados.

    Args:
    flow (dict): Un diccionario que contiene la configuración del flujo a crear en Node-RED.

    Returns:
    response: El objeto de respuesta de la solicitud que incluye el estado y los datos devueltos por el servidor.
              Retorna None si ocurre un error durante la solicitud.

    Ejemplo de uso:
    >>> flow = {
            "id": "12345",
            "label": "Mi flujo",
            "nodes": []
        }
    >>> response = crear_flow_nodered(flow)
    >>> print(response)
    """
    # Endpoint de Node-RED para la creación de flujos
    endpoint = f"{LOCAL_NodeRed}/flow"
    # Configuración de los headers de la solicitud HTTP
    headers = {"Authorization": token, "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    try:
        # Realizamos la solicitud POST para crear el flujo en Node-RED
        if 'token' in token:
            response = requests.post(endpoint, auth=HTTPBasicAuth(credenciales["username"], credenciales["password"]),
                                     json=flow)
        else:
            response = requests.post(endpoint, headers=headers, json=flow)
        print(response.json())
    except requests.RequestException as err:
        # Manejamos errores relacionados con la solicitud HTTP
        print('Error al conectar con el servidor. Detalles del error:', err)
        return None

    # Devolvemos el objeto de respuesta de la solicitud
    return response


## Cargamos los datos de dispositivos desde un archivo CSV específico del cliente.
# Este archivo contiene información detallada sobre los dispositivos, como nombres y tipos,
# que se utilizarán para configurar y gestionar los dispositivos en ThingsBoard.
# Leemos el archivo CSV que contiene los datos de los dispositivos para el cliente especificado.
df_devices = pd.read_csv(f'deploy/{Customer}/DeviceImport.csv')

# Generamos una lista de nombres de dispositivos a partir del DataFrame df_devices.
# Esta lista se utiliza para construir una cadena formateada específica que se necesita para configuraciones posteriores.

# Unimos los nombres de los dispositivos del DataFrame en una sola cadena, separada por '","'.
ListadoDevices = r'\",\"'.join(df_devices["name"])

# Construimos la cadena formateada que incluye los nombres de los dispositivos en el formato necesario para Node-RED.
# La cadena comienza con '["timestamp",' y cada nombre de dispositivo está entre comillas dobles escapadas.
ListadoDevices = 'ListadoDevices = [\\"timestamp\\",\\"' + ListadoDevices + r'\"]'

# Cargamos la plantilla de flujo ETL desde un archivo JSON y la personalizamos con los datos específicos del cliente.
# Abrimos el archivo de plantilla 'ETLflows.json' ubicado en el directorio 'Plantillas/ETLNodeRed'.
# Este archivo contiene la configuración base del flujo ETL en formato JSON.
fichero = open('deploy/Plantillas/ETLNodeRed/ETLflows.json', encoding="utf-8")

# Leemos el contenido completo del archivo y lo almacenamos en una variable.
ETLFlow = fichero.read()
# Cerramos el archivo para liberar recursos.
fichero.close()

# --- Despliegue del flujo PREVIO RAW DATA ---
with open('deploy/Plantillas/ETLNodeRed/PrevioRawFlow.json', encoding='utf-8') as f:
    prev_flow = f.read()

prev_flow = (prev_flow
             .replace("XXXXXXXXXX", Customer)
             .replace("ROOT_ThingsBoard", ROOT_Thingsboard)
             .replace("UsernameThingsBoard", TB_USER)
             .replace("PasswordThingsBoard", TB_PASS))

tok, _ = APIThingsboard.extract_token(credenciales_tb)
TOKEN = f"Bearer {tok}"
APIThingsboard.TOKEN = TOKEN
device_control_name = f"{Customer} Control"
print(f"Bucket de control (device): {device_control_name}")
deviceID = APIThingsboard.extract_id(device_control_name)

control_access_token = None
if deviceID:
    control_access_token = APIThingsboard.extract_Credentials(deviceID)
    print(f"control_access_token: {control_access_token}")
if control_access_token is not None:
    nodes_str = prev_flow.replace("TOKEN_CONTROL", control_access_token)
else:
    # Si no hay token (no existe el device, etc.), dejamos el placeholder para detectarlo en debug
    print(f"[WARN] No se encontró access token para '{device_control_name}'. "
          f"El flujo conservará TOKEN_CONTROL_XXXXXXXXXX como placeholder.")


FlowPrevio = {
    "id": f"PrevioRaw{Customer}",
    "label": f"RAW Data {Customer}",
    "nodes": json.loads(nodes_str),
    "configs": []
}

## Reemplazamos los marcadores de posición en la plantilla con los valores específicos del cliente.
# Reemplazamos "ROOT_ThingsBoard" con la ruta
ETLFlow = ETLFlow.replace("ROOT_ThingsBoard", ROOT_Thingsboard)
# Reemplazamos "XXXXXXXXXX" con el nombre del cliente.
ETLFlow = ETLFlow.replace("XXXXXXXXXX", Customer)
# Reemplazamos "YYYYYYYYYY" con la lista de dispositivos formateada.
ETLFlow = ETLFlow.replace("YYYYYYYYYY", ListadoDevices)
# Reemplazamos los marcadores de posición para los tokens de acceso específicos de los dispositivos de agregación.
ETLFlow = ETLFlow.replace("IDMEDIA1ID", IDMEDIA1ID)
ETLFlow = ETLFlow.replace("IDMEDIA5ID", IDMEDIA5ID)
ETLFlow = ETLFlow.replace("IDMEDIA10ID", IDMEDIA10ID)
ETLFlow = ETLFlow.replace("IDMEDIANA1ID", IDMEDIANA1ID)
ETLFlow = ETLFlow.replace("IDMEDIANA5ID", IDMEDIANA5ID)
ETLFlow = ETLFlow.replace("IDMEDIANA10ID", IDMEDIANA10ID)

## Creación del Flujo con los nodos
# Inicializamos un diccionario para definir el flujo en Node-RED.
Flow = {}
# Asignamos un ID único al flujo utilizando el nombre del cliente.
Flow["id"] = f"{Customer}ETL"
# Asignamos una etiqueta descriptiva al flujo que indique que es la etapa de preparación de datos para el cliente especificado.
Flow["label"] = f'Data preparation Stage {Customer}'
# Convertimos la cadena JSON personalizada de ETLFlow en un diccionario y la asignamos a la clave "nodes" del flujo.
# Esto incluye todos los nodos necesarios para el procesamiento ETL.
Flow["nodes"] = json.loads(ETLFlow)
# Inicializamos una lista vacía para configuraciones adicionales del flujo.
Flow["configs"] = []

## Extraemos el token de NodeRed
tok_nd = extract_token_nodered(credenciales_nd)
TOKEN_nd = f'Bearer {tok_nd}'

def update_flow_nodered(flow, credenciales, token='token'):
    """
    Carga un flujo de Node-RED, actualiza sus nodos basándose en un flujo local,
    y sube la versión actualizada.

    Args:
    - endpoint: URL del endpoint de Node-RED para acceder a los flujos.
    - credenciales: Diccionario con 'username' y 'password' para autenticación.
    - flujo_local: Lista de diccionarios que representa el flujo local a usar para actualizar nodos.

    Returns:
    - response: Objeto de respuesta de la solicitud POST.
    """
    flow_nodes = flow['nodes']
    # Endpoint de Node-RED para desplegar flujos
    endpoint = f"{LOCAL_NodeRed}/flows"
    # Configuración de los headers de la solicitud HTTP
    headers = {"Authorization": token, "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    # Obtener el flujo actual de Node-RED
    try:
        # Obtener los flujos actuales de Node-RED
        if 'token' in token:
            get_response = requests.get(endpoint,
                                        auth=HTTPBasicAuth(credenciales["username"], credenciales["password"]))
        else:
            get_response = requests.get(endpoint, headers=headers)
        if get_response.status_code == 200:
            flows_actuales = get_response.json()  # Lista de los nodos actuales en Node-RED
        else:
            print(f"Error al obtener los flujos actuales: {get_response.status_code}")
            return None
    except requests.RequestException as err:
        print('Error al conectar con el servidor para obtener los flujos:', err)
        return None

    # Mantener los nodos en la pestaña correcta
    nodos_tab = [d for d in flows_actuales if d.get("type") == "tab"]
    flow_z = None
    for tab in nodos_tab:
        if tab.get("label") == Flow['label']:
            flow_z = tab.get('id')  # Identificador de la pestaña correcta

    if flow_z is None:
        print(f"No se encontró una pestaña con el label: {Flow['label']}")
        return None

    # Crear una lista para almacenar nodos actualizados y nuevos
    nuevos_nodos = []

    # Iterar sobre los nodos locales y actualizarlos si ya existen en Node-RED
    for nodo_local in Flow['nodes']:
        nodo_existente = False

        # Verificar si el nodo local ya existe en el flujo actual de Node-RED
        for nodo_actual in flows_actuales:
            if nodo_actual.get('id') == nodo_local.get('id'):
                # Si el nodo existe, actualizarlo
                for key, value in nodo_local.items():
                    if key != 'z':  # No sobrescribir 'z' para mantener la pestaña
                        nodo_actual[key] = value
                nodo_existente = True

        # Si el nodo no existe, añadirlo a la lista de nuevos nodos
        if not nodo_existente:
            # Asegúrate de asignar el valor correcto de 'z' al nuevo nodo para que esté en la pestaña correcta
            nodo_local['z'] = flow_z
            nuevos_nodos.append(nodo_local)
            # print(f"Nodo nuevo añadido: {nodo_local}")

    # Añadir los nuevos nodos al flujo actual
    flows_actuales.extend(nuevos_nodos)

    try:
        # Realizar la solicitud POST para desplegar los flujos actualizados
        if 'token' in token:
            response = requests.post(endpoint, auth=HTTPBasicAuth(credenciales["username"], credenciales["password"]),
                                     json=flows_actuales)
        else:
            response = requests.post(endpoint, headers=headers, json=flows_actuales)
        if response.status_code == 204:
            print("Flujos desplegados correctamente.")
        else:
            print(f"Error al desplegar los flujos: {response.status_code}")
            return None
    except requests.RequestException as err:
        print('Error al conectar con el servidor para desplegar los flujos:', err)
        return None

    return response

## Creación del flujo en Node-RED utilizando la función crear_flow_nodered
# Utilizamos la función crear_flow_nodered para crear el flujo en Node-RED
# utilizando el diccionario Flow configurado anteriormente.
#response = crear_flow_nodered(flow=Flow, credenciales=credenciales_nd)
response = crear_flow_nodered(flow=Flow, credenciales=credenciales_nd, token=TOKEN_nd)
response_pre = crear_flow_nodered(flow=FlowPrevio, credenciales=credenciales_nd, token=TOKEN_nd)

# Llamamos a la función para actualizar los flujos en Node-RED
#response = update_flow_nodered(flow=Flow, credenciales=credenciales_nd)
response = update_flow_nodered(flow=Flow, credenciales=credenciales_nd, token=TOKEN_nd)
response_pre = update_flow_nodered(flow=FlowPrevio, credenciales=credenciales_nd, token=TOKEN_nd)

# Imprimimos la respuesta de la solicitud para verificar que el flujo se ha actualizado correctamente.
print(response)
print("Flujo PREVIO RAW desplegado/actualizado: \n", response_pre)
