# Parámetros Iniciales
# ROOT
ROOT_Thingsboard = "http://172.25.0.2:9090"
ROOT_NodeRed = "http://172.25.0.3:1880"
LOCAL_Thingsboard = "http://localhost:9090"
LOCAL_NodeRed = "http://localhost:1880"

# Número de RuleChains que se extraerán en cada página de consulta a ThingsBoard.
PageSize = 4

# Parámetros para la creación de dispositivos estadísticos:
# Estos dispositivos calcularán estadísticas como la media y la mediana para diferentes ventanas de tiempo.
Estadisticos = ["Media", "Mediana"]
Ventanas = [1, 5, 10]  # Ventanas de tiempo para el cálculo de estadísticas, en minutos.

# Parámetros para la creación de buckets para modelos:
# Estos buckets agruparán dispositivos según los modelos especificados.
Modelos = ["M1", "M2", "M3"]

# Listado de Tipos de Buckets
TiposBuckets=["Device","Buckets","Models","Estimaciones Modelo", "Estimaciones relativo Modelo", "Matriz Relacion","Niveles Modelos","RAW","Control"]

# Cargamos las librerías necesarias para el notebook
import pandas as pd
import json
import APIThingsboard

## Cargamos datos del cliente
Parametros_cliente_json = open("deploy/Client.json")
Parametros_cliente = json.load(Parametros_cliente_json)
Parametros_cliente_json.close()
Customer = Parametros_cliente["Client"]

## Cargamos las credenciales de las plataformas
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

### OBTENCIÓN DE TOKEN THINGSBOARD
# Proceso de Extracción del Token del Tenant
# Utilizamos la función extract_token del módulo APIThingsboard para obtener el token de autenticación y el token de actualización
# usando las credenciales del tenant previamente cargadas.
tok, refreshTok = APIThingsboard.extract_token(credenciales_tb)

# Formateamos el token obtenido en el formato adecuado para su uso en las cabeceras de las solicitudes HTTP.
# El prefijo 'Bearer' se utiliza para indicar que el tipo de autenticación es un token portador (Bearer Token),
# que es un tipo común de esquema de autorización.
TOKEN = f'Bearer {tok}'

# Configuración de parámetros globales en el módulo APIThingsboard
# Establecemos el token de autenticación obtenido anteriormente como una variable global dentro del módulo APIThingsboard.
# Esto asegura que todas las funciones dentro de APIThingsboard que realicen solicitudes HTTP a ThingsBoard
# utilizarán este token para autenticarse correctamente.
APIThingsboard.TOKEN = TOKEN

# Asignamos el tamaño de página global, que determina el número de resultados por página que se recuperan en las solicitudes paginadas.
# Configurar este parámetro globalmente permite que todas las funciones que requieran paginación usen este mismo tamaño de página.
APIThingsboard.PageSize = PageSize

# Asignamos la ruta de la URL
# Configurar este parámetro globalmente permite que todas las funciones apunten a la misma URL
APIThingsboard.Root = LOCAL_Thingsboard
APIThingsboard.root_nodered = ROOT_NodeRed

### CREACION DE CUSTOMER
# Comprobamos si el cliente existe (Old) o no (New). En caso de que no exista se crea. En ambos casos se devuelve el ID del Cliente.
# Utilizamos la función clienteIDStatus del módulo APIThingsboard para verificar la existencia del cliente
# especificado por la variable 'Customer'. Esta función devuelve el ID del cliente y su estado.
# Si el cliente no existe, la función automáticamente lo crea y devuelve un estado 'New',
# de lo contrario devuelve el estado 'Old' indicando que el cliente ya existe.
CustomerId, CustomerStatus = APIThingsboard.clienteIDStatus(Customer)

# Asignamos el ID del cliente a una variable global dentro del módulo APIThingsboard para su uso en otras operaciones.
APIThingsboard.CustomerId = CustomerId
# Imprimimos el ID del cliente y su estado para verificar y documentar la operación.
print(CustomerId)
print(CustomerStatus)

### CREACION DE RULECHAINS
## Extraemos o creamos perfiles de dispositivo específicos para diferentes categorías y almacenamos sus IDs.
dicRuleChainsID={}
for bucket in TiposBuckets:
    dicRuleChainsID[bucket] = APIThingsboard.extraer_DevicesRuleChainId(Customer, bucket)

### CREACION DE PROFILES
## Extraemos o creamos perfiles de dispositivo específicos para diferentes categorías y almacenamos sus IDs.
dicProfilesID={}
for bucket in TiposBuckets:
    dicProfilesID[bucket] = APIThingsboard.extraer_DevicesProfile(Customer, bucket)

### CREACION de DEVICES y EXTRACCION DE IDs
# Cargamos los datos de dispositivos desde un archivo CSV específico del cliente.
# Leemos el archivo CSV que contiene información de los dispositivos para el cliente especificado. Este archivo incluye detalles
# como el nombre del dispositivo, tipo, y otras configuraciones necesarias para su creación en ThingsBoard.
df_devices = pd.read_csv(f'deploy/{Customer}/DeviceImport.csv')

### CREACIÓN DE DISPOSITIVOS EN MASA Y EXTRACCIÓN DE IDs Y TOKENS DE ACCESO
# Utilizamos la función crear_devicesBulk para crear dispositivos en ThingsBoard basados en los datos del DataFrame df_devices.
# Esta función también asigna a cada dispositivo a un cliente específico y recupera los IDs y tokens de acceso.

# Procesamos el DataFrame df_devices, que debe contener al menos las columnas 'name' y 'type' para cada dispositivo.
# La función crear_devicesBulk devuelve el DataFrame actualizado con dos columnas adicionales:
# 'devicesId' que contiene los IDs de los dispositivos creados, y 'accessToken' que contiene los tokens de acceso para cada dispositivo.
df_devices = APIThingsboard.crear_devicesBulk(df_devices)

### GUARDADO DE DISPOSITIVOS Y SUS CREDENCIALES A UN ARCHIVO CSV
# Guardamos el DataFrame actualizado que contiene los nombres, tipos, IDs de dispositivos y tokens de acceso a un archivo CSV.
# Este archivo servirá como registro de todos los dispositivos creados junto con sus credenciales de acceso.

# El archivo se guarda en el directorio específico del cliente, asegurando que la información esté organizada y sea fácil de acceder.
# No incluimos el índice del DataFrame en el archivo CSV para mantener la estructura de datos limpia y útil.
df_devices.to_csv(f'deploy/{Customer}/DeviceimportCredentials_{Customer}.csv', index=False)

# Imprimimos una confirmación para verificar que el archivo ha sido guardado correctamente.
print(f"Archivo guardado: deploy/{Customer}/DeviceimportCredentials_{Customer}.csv")

### CREACION de DEVICES AUXILIARES y EXTRACCION DE IDs
### CREACIÓN DE DISPOSITIVOS AUXILIARES Y EXTRACCIÓN DE IDs
# Creamos un DataFrame para organizar la información necesaria para la creación de dispositivos auxiliares.
# Estos dispositivos se utilizan para realizar agregaciones, modelar datos y otras funciones específicas dentro de ThingsBoard.
# Listas para almacenar los nombres y tipos de dispositivos auxiliares.
name = []
tipo = []

# Combinamos los tipos de estadísticos con las ventanas de tiempo para crear dispositivos de agregación.
# Estos dispositivos se encargarán de realizar cálculos estadísticos como la media y mediana para diferentes ventanas de tiempo.
for a in Estadisticos:
    for b in Ventanas:
        name.append(f"{Customer} Aggregation {a} Ventana {b}seg")
        tipo.append(f"{Customer} Buckets")

# Creamos dispositivos para modelos, estimaciones y matrices de relación.
# Estos dispositivos son específicos para cada modelo y se utilizan para tareas como la modelación de datos y análisis.
for m in Modelos:
    name.append(f"{Customer} Model {m}")
    tipo.append(f"{Customer} Models")
    name.append(f"{Customer} Estimaciones {m}")
    tipo.append(f"{Customer} Estimaciones Modelo")
    name.append(f"{Customer} Estimaciones relativo {m}")
    tipo.append(f"{Customer} Estimaciones relativo Modelo")
    name.append(f"{Customer} Matriz Model {m}")
    tipo.append(f"{Customer} Matriz Relacion")
    name.append(f"{Customer} Niveles Model {m}")
    tipo.append(f"{Customer} Niveles Modelos")
    name.append(f"{Customer} Control")
    tipo.append(f"{Customer} Control")
    name.append(f"{Customer} RAW Data")
    tipo.append(f"{Customer} RAW")

# Generamos un DataFrame con los nombres y tipos de dispositivos configurados.
df_devices_aux = pd.DataFrame({"name": name, "type": tipo})

# Usamos la función crear_devicesBulk para crear todos los dispositivos auxiliares especificados en el DataFrame.
# Esta función también asigna cada dispositivo a un cliente y recupera los IDs y tokens de acceso.
df_devices_aux = APIThingsboard.crear_devicesBulk(df_devices_aux)

# Guardamos el DataFrame actualizado, que ahora incluye IDs y tokens de acceso, a un archivo CSV.
# Este archivo se almacena en el directorio específico del cliente para fácil acceso y referencia futura.
df_devices_aux.to_csv(f'deploy/{Customer}/OthersimportCredentials_{Customer}.csv', index=False)

# Imprimimos una confirmación para indicar que el archivo ha sido guardado correctamente.
print(f"Archivo guardado: deploy/{Customer}/OthersimportCredentials_{Customer}.csv")
