# Parámetros Iniciales
ROOT_Thingsboard = "http://172.25.0.2:9090"
ROOT_NodeRed = "http://172.25.0.3:1880"
LOCAL_Thingsboard = "http://localhost:9090"
LOCAL_NodeRed = "http://localhost:1880"

# Abrimos el archivo 'ParametrosConfiguracion.txt' que contiene las credenciales y parámetros de configuración en formato JSON.
fichero = open('deploy/ParametrosConfiguracion.txt')

# Cargamos las librerías necesarias
import os
import pandas as pd
import json
import APIThingsboard
import requests
from requests.auth import HTTPBasicAuth

## Cargamos las credenciales de las plataformas

# Leemos el contenido completo del archivo y lo almacenamos en una variable.
ParametrosConfiguracion = fichero.read()

# Cerramos el archivo para liberar recursos.
fichero.close()

# Convertimos la cadena de texto JSON leída del archivo en un diccionario de Python para un acceso más fácil a los parámetros.
Parametros = json.loads(ParametrosConfiguracion)

## Extraemos las credenciales de Tenant de los parámetros de configuración cargados previamente.
# Las credenciales del Tenant se utilizan para autenticarse y realizar operaciones en la plataforma ThingsBoard bajo el contexto de este Tenant.
credenciales_tb = Parametros["CredencialesTenantThings"]

## Cargamos datos del cliente
Parametros_cliente_json = open("deploy/Client.json")
Parametros_cliente = json.load(Parametros_cliente_json)
Customer = Parametros_cliente["Client"]
Parametros_cliente_json.close()

## Proceso de Extracción del Token del Tenant
# Utilizamos la función extract_token del módulo APIThingsboard para obtener el token de autenticación y el token de actualización
# usando las credenciales del tenant previamente cargadas.
tok, refreshTok = APIThingsboard.extract_token(credenciales_tb)
## Formateamos el token obtenido en el formato adecuado para su uso en las cabeceras de las solicitudes HTTP.
# El prefijo 'Bearer' se utiliza para indicar que el tipo de autenticación es un token portador (Bearer Token),
# que es un tipo común de esquema de autorización.
TOKEN = f'Bearer {tok}'

## Configuración de parámetros globales en el módulo APIThingsboard
# Establecemos el token de autenticación obtenido anteriormente como una variable global dentro del módulo APIThingsboard.
# Esto asegura que todas las funciones dentro de APIThingsboard que realicen solicitudes HTTP a ThingsBoard
# utilizarán este token para autenticarse correctamente.
APIThingsboard.TOKEN = TOKEN

## Asignamos la ruta de la URL
# Configurar este parámetro globalmente permite que todas las funciones apunten a la misma URL
APIThingsboard.Root = LOCAL_Thingsboard

### CREACION de DEVICES y EXTRACCION DE IDs

## Cargamos los datos de dispositivos desde un archivo CSV específico del cliente.
# Leemos el archivo CSV que contiene información de los dispositivos para el cliente especificado. Este archivo incluye detalles
# como el nombre del dispositivo, tipo, y otras configuraciones necesarias para su creación en ThingsBoard.
df_devices_base = pd.read_csv(f'deploy/Plantillas/StandardDevices/Buckets.csv')

### CREACIÓN DE DISPOSITIVOS EN MASA Y EXTRACCIÓN DE IDs Y TOKENS DE ACCESO
# Utilizamos la función crear_devicesBulk para crear dispositivos en ThingsBoard basados en los datos del DataFrame df_devices.
# Esta función también asigna a cada dispositivo a un cliente específico y recupera los IDs y tokens de acceso.

# Procesamos el DataFrame df_devices, que debe contener al menos las columnas 'name' y 'type' para cada dispositivo.
# La función crear_devicesBulk devuelve el DataFrame actualizado con dos columnas adicionales:
# 'devicesId' que contiene los IDs de los dispositivos creados, y 'accessToken' que contiene los tokens de acceso para cada dispositivo.
df_devices_base = APIThingsboard.crear_devicesBulk(df_devices_base)

### GUARDADO DE DISPOSITIVOS Y SUS CREDENCIALES A UN ARCHIVO CSV
# Guardamos el DataFrame actualizado que contiene los nombres, tipos, IDs de dispositivos y tokens de acceso a un archivo CSV.
# Este archivo servirá como registro de todos los dispositivos creados junto con sus credenciales de acceso.

# El archivo se guarda en el directorio específico del cliente, asegurando que la información esté organizada y sea fácil de acceder.
# No incluimos el índice del DataFrame en el archivo CSV para mantener la estructura de datos limpia y útil.
os.makedirs(f"deploy/{Customer}", exist_ok=True)
df_devices_base.to_csv(f'deploy/{Customer}/DeviceimportCredentials_CORE.csv', index=False)

# Extraemos las credenciales específicas para Node-RED de los parámetros de configuración cargados previamente.
# Las credenciales de Node-RED se utilizan para autenticarse y realizar operaciones en Node-RED.
credenciales_nd = Parametros["CredencialesNodeRed"]


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
    #endpoint = f"{ROOT_NodeRed}/auth/token"
    endpoint = f"{LOCAL_NodeRed}/auth/token"
    print(endpoint)
    # Convertimos las credenciales a formato JSON
    data = json.dumps(credenciales)
    print(data)

    # Configuramos los headers para la solicitud HTTP
    headers = {"Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}

    try:
        # Realizamos la solicitud POST para obtener el token
        response = requests.post(endpoint, headers=headers, data=data)  # .json()
        print(response)
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
    print("endpoint")
    print(endpoint)
    # Configuración de los headers de la solicitud HTTP
    headers = {"Authorization": token, "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    #print("headers")
    #print(headers)
    # Convertimos el diccionario del flujo a formato JSON
    # data = json.dumps(flow)
    # print(data)

    try:
        #print("credenciales")
        #print(credenciales)
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


deviceIdClientesNiveles = \
df_devices_base.loc[df_devices_base["name"] == "CLIENTES Niveles de Criticidad", "devicesId"].values[0]
accessTokenClientesNiveles = \
df_devices_base.loc[df_devices_base["name"] == "CLIENTES Niveles de Criticidad", "accessToken"].values[0]

deviceIdNivelesDescartes = \
df_devices_base.loc[df_devices_base["name"] == "Niveles Model General Descartados", "devicesId"].values[0]
accessTokenNivelesDescartes = \
df_devices_base.loc[df_devices_base["name"] == "Niveles Model General Descartados", "accessToken"].values[0]

UsernameThingsBoard = credenciales_nd["username"]
PasswordThingsBoard = credenciales_nd["password"]
print(f"user: {UsernameThingsBoard}")
print(f"pass: {PasswordThingsBoard}")

## Cargamos la plantilla de flujo ETL desde un archivo JSON y la personalizamos con los datos específicos del cliente.
# Abrimos el archivo de plantilla 'ETLflows.json' ubicado en el directorio 'Plantillas/ETLNodeRed'.
# Este archivo contiene la configuración base del flujo ETL en formato JSON.
fichero = open('deploy/Plantillas/ETLNodeRed/flows Critical Levels.json', encoding="utf-8")

# Leemos el contenido completo del archivo y lo almacenamos en una variable.
ETLFlow = fichero.read()

# Cerramos el archivo para liberar recursos.
fichero.close()

# Reemplazamos los marcadores de posición en la plantilla con los valores específicos del cliente.
# Reemplazamos "ROOT_ThingsBoard" con el nombre de la ruta raiz de la URL
#ETLFlow = ETLFlow.replace("ROOT_ThingsBoard", ROOT_Thingsboard)
ETLFlow = ETLFlow.replace("ROOT_ThingsBoard", ROOT_Thingsboard)

# Reemplazamos "deviceId" y "AccessToken" de los buckets globales asociados a los niveles de criticidad
ETLFlow = ETLFlow.replace("accessTokenClientesNiveles", accessTokenClientesNiveles)
ETLFlow = ETLFlow.replace("deviceIdClientesNiveles", deviceIdClientesNiveles)
ETLFlow = ETLFlow.replace("deviceIdNivelesDescartes", deviceIdNivelesDescartes)

# Incluimos usuario y contraseña en el flujo
ETLFlow = ETLFlow.replace("UsernameThingsBoard", credenciales_tb["username"])
ETLFlow = ETLFlow.replace("PasswordThingsBoard", credenciales_tb["password"])

## Creación del Flujo con los nodos
# Inicializamos un diccionario para definir el flujo en Node-RED.
Flow = {}

# Asignamos el ID Critical Level
Flow["id"] = "Critical Level"

# Asignamos una etiqueta descriptiva al flujo.
Flow["label"] = 'Critical Level'

# Convertimos la cadena JSON personalizada de ETLFlow en un diccionario y la asignamos a la clave "nodes" del flujo.
# Esto incluye todos los nodos necesarios para el procesamiento ETL.
Flow["nodes"] = json.loads(ETLFlow)
for dic in Flow["nodes"]:
    dic['z'] = Flow["id"]

# Inicializamos una lista vacía para configuraciones adicionales del flujo.
Flow["configs"] = []

## Creación del flujo en Node-RED utilizando la función crear_flow_nodered
tok_nd = extract_token_nodered(credenciales_nd)
TOKEN_nd = f'Bearer {tok_nd}'
# Utilizamos la función crear_flow_nodered para crear el flujo en Node-RED
#response = crear_flow_nodered(flow=Flow, credenciales=credenciales_nd)
response = crear_flow_nodered(flow=Flow, credenciales=credenciales_nd, token=TOKEN_nd)
# Imprimimos la respuesta de la solicitud para verificar que el flujo se ha creado correctamente.
print(response)

# Llamamos a la función para actualizar los flujos en Node-RED
#response = update_flow_nodered(flow=Flow, credenciales=credenciales_nd)
response = update_flow_nodered(flow=Flow, credenciales=credenciales_nd, token=TOKEN_nd)
# Imprimimos la respuesta de la solicitud para verificar que el flujo se ha actualizado correctamente.
print(response)


