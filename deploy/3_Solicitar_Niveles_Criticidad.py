# Parámetros Iniciales
ROOT_Thingsboard = "http://thingsboard:9090"
LOCAL_Thingsboard = "http://localhost:9090"

## Cargamos las librerías necesarias
import requests
import pandas as pd
import json
import APIThingsboard

## Cargamos datos del cliente
Parametros_cliente_json = open("deploy/Client.json")
Parametros_cliente = json.load(Parametros_cliente_json)
Parametros_cliente_json.close()
# CLIENTE
CLIENTE = Parametros_cliente["Client"]
# MODELO
MODELO = Parametros_cliente["Model"]

## Leemos fichero con dispositivos Core
df_buckets_core = pd.read_csv(f"{CLIENTE}/DeviceimportCredentials_CORE.csv")
# Abrimos el archivo 'ParametrosConfiguracion.txt' que contiene las credenciales y parámetros de configuración en formato JSON.
fichero = open('deploy/ParametrosConfiguracion.txt')
# Leemos el contenido completo del archivo y lo almacenamos en una variable.
ParametrosConfiguracion = fichero.read()
# Cerramos el archivo para liberar recursos.
fichero.close()

# Convertimos la cadena de texto JSON leída del archivo en un diccionario de Python para un acceso más fácil a los parámetros.
Parametros = json.loads(ParametrosConfiguracion)

# Extraemos las credenciales de Tenant de los parámetros de configuración cargados previamente.
# Las credenciales del Tenant se utilizan para autenticarse y realizar operaciones en la plataforma ThingsBoard bajo el contexto de este Tenant.
credenciales_tb = Parametros["CredencialesTenantThings"]

## Proceso de Extracción del Token del Tenant
# Utilizamos la función extract_token del módulo APIThingsboard para obtener el token de autenticación y el token de actualización
# usando las credenciales del tenant previamente cargadas.
tok, refreshTok = APIThingsboard.extract_token(credenciales_tb)

# Formateamos el token obtenido en el formato adecuado para su uso en las cabeceras de las solicitudes HTTP.
# El prefijo 'Bearer' se utiliza para indicar que el tipo de autenticación es un token portador (Bearer Token),
# que es un tipo común de esquema de autorización.
TOKEN = f'Bearer {tok}'

## Configuración de parámetros globales en el módulo APIThingsboard
# Establecemos el token de autenticación obtenido anteriormente como una variable global dentro del módulo APIThingsboard.
# Esto asegura que todas las funciones dentro de APIThingsboard que realicen solicitudes HTTP a ThingsBoard
# utilizarán este token para autenticarse correctamente.
APIThingsboard.TOKEN = TOKEN

# Asignamos el tamaño de página global, que determina el número de resultados por página que se recuperan en las solicitudes paginadas.
# Configurar este parámetro globalmente permite que todas las funciones que requieran paginación usen este mismo tamaño de página.
# APIThingsboard.PageSize = PageSize

# Asignamos la ruta de la URL
# Configurar este parámetro globalmente permite que todas las funcionesapunten a la misma URL
APIThingsboard.Root = LOCAL_Thingsboard

deviceIdClientesNiveles = df_buckets_core.loc[df_buckets_core["name"]=="CLIENTES Niveles de Criticidad","devicesId"].values[0]

def extract_telemetry(N,deviceType, deviceID, keys):
    params = {}
    params["keys"]= keys
    params["startTs"] = 1000000000000
    params["endTs"] = 9999999999999
    params["limit"] = N
    params["orderBy"] = "DESC"
    endpoint = f"{LOCAL_Thingsboard}/api/plugins/telemetry/"+str(deviceType)+"/"+str(deviceID)+"/values/timeseries"
    headers = {"Authorization": TOKEN,"Content-Type":"application/json;charset=UTF-8", "Accept":"application/json"}
    try:
        response = requests.get(endpoint, headers=headers, params = params).json()
    except Error as err:
        print('La página no existe. Codigo: '+str(err.code))
        print(err.headers)
        print(err.reason)
        #sys.exit()
        return None
    return response

## Petición de Datos de Niveles en ThingsBoard
SolicitudNiveles = extract_telemetry(1000,"DEVICE",deviceIdClientesNiveles,"Cliente,Modelo,NumNivel,Cota,FechaInicio,FechaFin,Activo")

### Proceso de Transformación de Telemetría
datosTrans = {key: {x['ts']:x["value"] for x in SolicitudNiveles[key]} for key in SolicitudNiveles.keys()}

## Proceso de transformación a DataFrame
NivelesCriticidad = pd.DataFrame.from_dict(datosTrans,orient="columns")

## SELECCION DE NIVELES ACTIVOS DEL CLIENTE
NivlesActivos = NivelesCriticidad[(NivelesCriticidad["Cliente"]==CLIENTE) & (NivelesCriticidad["Activo"]=="1") & (NivelesCriticidad["Modelo"]==MODELO)]

