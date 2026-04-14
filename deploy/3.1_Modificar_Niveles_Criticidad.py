# Parámetros Iniciales
ROOT_Thingsboard = "http://thingsboard:9090"
LOCAL_Thingsboard = "http://localhost:9090"

## Cargamos las librerías necesarias
import pandas as pd
import json
from datetime import datetime
import APIThingsboard
import os

## Cargamos datos del cliente
Parametros_cliente_json = open("deploy/Client.json")
Parametros_cliente = json.load(Parametros_cliente_json)
Parametros_cliente_json.close()
# CLIENTE
CLIENTE = Parametros_cliente["Client"]
# MODELO
MODELO = os.environ["MODEL"]
# NIVELES A CAMBIAR
NIVEL = os.environ["LEVEL"]
# VALOR NIVEL
VALOR = os.environ["VALUE"]

# Leemos fichero con dispositivos Core
df_buckets_core = pd.read_csv(f"{CLIENTE}/DeviceimportCredentials_CORE.csv")
# Abrimos el archivo 'ParametrosConfiguracion.txt' que contiene las credenciales y parámetros de configuración en formato JSON.
fichero = open('deploy/ParametrosConfiguracion.txt')

# Leemos el contenido completo del archivo y lo almacenamos en una variable.
ParametrosConfiguracion = fichero.read()

# Cerramos el archivo para liberar recursos.
fichero.close()

# Convertimos la cadena de texto JSON leída del archivo en un diccionario de Python para un acceso más fácil a los parámetros.
Parametros = json.loads(ParametrosConfiguracion)

## Extraemos las credenciales de Tenant de los parámetros de configuración cargados previamente.
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
accessTokenClientesNiveles = df_buckets_core.loc[df_buckets_core["name"]=="CLIENTES Niveles de Criticidad","accessToken"].values[0]

## Petición de Datos de Niveles en ThingsBoard
SolicitudNiveles = APIThingsboard.extract_telemetry(1000,"DEVICE",deviceIdClientesNiveles,"Cliente,Modelo,NumNivel,Cota,FechaInicio,FechaFin,Activo")

### Proceso de Transformación de Telemetría
datosTrans = {key: {x['ts']:x["value"] for x in SolicitudNiveles[key]} for key in SolicitudNiveles.keys()}

## Proceso de transformación a DataFrame
NivelesCriticidad = pd.DataFrame.from_dict(datosTrans,orient="columns")

## SELECCION DE NIVELES ACTIVOS DEL CLIENTE
NivelesActivos = NivelesCriticidad[(NivelesCriticidad["Cliente"]==CLIENTE) & (NivelesCriticidad["Activo"]=="1") & (NivelesCriticidad["Modelo"]==MODELO)]

### BLOQUE DE ACTUALIZACIÓN DE NIVELES DE CRITICIDAD
FechaHoy = datetime.now().strftime("%d\\/%m\\/%Y %H:%M")

IntNiveles=[int(x) for x in NivelesActivos["NumNivel"].to_list()]
maxNivel = int(NivelesActivos["NumNivel"].max())
maxNivel = max(IntNiveles)

Registro=NivelesActivos[NivelesActivos["NumNivel"]==str(NIVEL)].iloc[0]

if ((NIVEL not in IntNiveles) & (NIVEL !=maxNivel+1)):
    print("El Nivel no tiene el formato o valor adecuado. Recuerda que tiene que ser un número entero repsentando el nivel y esar comprendido entre 1 y el máximo de valores posibles")
elif NIVEL == 1:
    if (float(NivelesActivos["Cota"][NivelesActivos["NumNivel"]=="2"].values[0])> VALOR):
        Registro=NivelesActivos[NivelesActivos["NumNivel"]==str(NIVEL)].iloc[0]
        response = APIThingsboard.update_nivel_crit(Registro.Cliente,Registro.Modelo,Registro.NumNivel,Registro.Cota,Registro.FechaInicio,FechaHoy,0,deviceIdClientesNiveles,Registro.name )
        #response = update_nivel_crit(Registro.Cliente,Registro.Modelo,Registro.NumNivel,Registro.Cota,Registro.FechaInicio,FechaHoy,0,deviceIdClientesNiveles,Registro.name )
        response = APIThingsboard.post_nivel_crit(CLIENTE,MODELO,NIVEL,VALOR,FechaHoy,"NULL",1, accessTokenClientesNiveles)
        #response2 = post_nivel_crit(CLIENTE,MODELO,NIVEL,VALOR,FechaHoy,"NULL",1, accessTokenClientesNiveles)

    else:
        print("El valor es superior o igual al asociado a la cota 2")
elif NIVEL == (maxNivel+1):
    if (float(NivelesActivos["Cota"][NivelesActivos["NumNivel"]==str(maxNivel)].values[0])> VALOR):
        response = APIThingsboard.post_nivel_crit(CLIENTE,MODELO,NIVEL,VALOR,FechaHoy,"NULL",1, accessTokenClientesNiveles)
        #response = post_nivel_crit(CLIENTE,MODELO,NIVEL,VALOR,FechaHoy,"NULL",1, accessTokenClientesNiveles)
    else:
        print(f"El valor es inferior o igual al asociado a la cota anterios número {str(maxNivel)}")
else:
    if (float(NivelesActivos["Cota"][NivelesActivos["NumNivel"]==str(NIVEL+1)].values[0])>VALOR):
        if (float(NivelesActivos["Cota"][NivelesActivos["NumNivel"]==str(NIVEL-1)].values[0])<VALOR):
            Registro=NivelesActivos[NivelesActivos["NumNivel"]==str(NIVEL)].iloc[0]
            print(f"ACTUALIZAR_{NIVEL}")
            response = APIThingsboard.update_nivel_crit(Registro.Cliente,Registro.Modelo,Registro.NumNivel,Registro.Cota,Registro.FechaInicio,FechaHoy,0,deviceIdClientesNiveles,Registro.name )
            #response = update_nivel_crit(Registro.Cliente,Registro.Modelo,Registro.NumNivel,Registro.Cota,Registro.FechaInicio,FechaHoy,0,deviceIdClientesNiveles,Registro.name )
            print(f"CREAR_{NIVEL}")
            response = APIThingsboard.post_nivel_crit(CLIENTE,MODELO,NIVEL,VALOR,FechaHoy,"NULL",1, accessTokenClientesNiveles)
            #response = post_nivel_crit(CLIENTE,MODELO,NIVEL,VALOR,FechaHoy,"NULL",1, accessTokenClientesNiveles)

        else:
            print(f"El valor es inferior o igual al asociado a la cota anterios número {str(NIVEL-1)}")
    else:
        print(f"El valor es superior o igual al asociado a la cota posterior número {str(NIVEL+1)}")


