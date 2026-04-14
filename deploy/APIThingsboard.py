# Cargamos las librerías necesarias
import requests
import pandas as pd
import json

# Parámetros Globales
TOKEN = None
PageSize = None
CustomerId = None
Root = "http://localhost:9090"
root_nodered = "http://172.25.0.3:1880"


# Función que devuelve el token y el refresh token de ThingsBoard
def extract_token(credenciales):
    """
    Esta función realiza una solicitud POST a la API de ThingsBoard para autenticarse usando las credenciales
    proporcionadas y devuelve un token de acceso y un token de actualización.

    Args:
    credenciales (dict): Un diccionario que contiene las credenciales del usuario (usualmente 'username' y 'password').

    Returns:
    tuple: Retorna un par (token, refresh_token) donde 'token' es el token de acceso y 'refresh_token' es el token de actualización.
    None: Retorna None si ocurre algún error durante la solicitud o el proceso de autenticación.

    Ejemplo de uso:
    >>> credenciales = {"username": "usuario", "password": "contraseña"}
    >>> token, refresh_token = extract_token(credenciales)
    """
    endpoint = f"{Root}/api/auth/login"
    print(endpoint)
    data = json.dumps(credenciales)
    print(data)
    headers = {"Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    try:
        response = requests.post(endpoint, headers=headers, data=data).json()
    except Error as err:
        print('La página no existe. Codigo: ' + str(err.code))
        print(err.headers)
        print(err.reason)
        return None
    return response['token'], response['refreshToken']


# Función de Creación del cliente
def crear_cliente(customer):
    """
    Envía una solicitud POST para crear un nuevo cliente en el sistema ThingsBoard utilizando el título proporcionado.

    Args:
    customer (str): El nombre del cliente que se desea crear.

    Returns:
    response: Objeto de respuesta de la solicitud que incluye el estado y los datos devueltos por el servidor.
    None: Retorna None si ocurre un error en la conexión o durante la solicitud.

    Ejemplo de uso:
    >>> nombre_cliente = "Nuevo Cliente"
    >>> respuesta = crear_cliente(nombre_cliente)
    >>> print(respuesta.status_code)
    >>> if respuesta.status_code == 200:
    ...     print("Cliente creado correctamente.")
    ... else:
    ...     print("Error al crear el cliente.")
    """
    endpoint = f"{Root}/api/customer"
    headers = {"Authorization": TOKEN, "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    data = '{"title":"' + customer + '"}'
    # print(data)
    try:
        response = requests.post(endpoint, headers=headers, data=data)
        # print(response.status_code)
        # print(response.json())
    except Error as err:
        print('La página no existe. Codigo: ' + str(err.code))
        print(err.headers)
        print(err.reason)
        # sys.exit()
        return None
    return response


# Función de Creación del cliente
def extraer_cliente_title(customer):
    """
    Realiza una solicitud GET para buscar clientes en ThingsBoard según el título del cliente proporcionado.

    Args:
    customer (str): El título del cliente que se desea buscar.

    Returns:
    response: Objeto de respuesta de la solicitud que incluye el estado y los datos devueltos por el servidor si la búsqueda fue exitosa.
    None: Retorna None si ocurre un error en la conexión o durante la solicitud.

    Ejemplo de uso:
    >>> titulo_cliente = "Cliente Existente"
    >>> respuesta = extraer_cliente_title(titulo_cliente)
    >>> print(respuesta.status_code)
    >>> if respuesta.status_code == 200:
    ...     print("Búsqueda exitosa.")
    ... else:
    ...     print("Error en la búsqueda del cliente.")
    """
    # endpoint = Root+"/api/tenant/customers?customerTitle="+customer
    endpoint = f"{Root}/api/tenant/customers?customerTitle={customer}"
    headers = {"Authorization": TOKEN, "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    try:
        response = requests.get(endpoint, headers=headers)
        # print(response.status_code)
        # print(response.json())
    except Error as err:
        print('La página no existe. Codigo: ' + str(err.code))
        print(err.headers)
        print(err.reason)
        # sys.exit()
        return None
    return response


def clienteIDStatus(customer):
    """
    Verifica si un cliente existe en ThingsBoard mediante su título. Si no existe, lo crea y registra sus datos en un archivo.
    Retorna el ID del cliente y su estado como 'New' si fue creado, 'Old' si ya existía, o 'Otros' para otros casos.

    Args:
    customer (str): El título del cliente a verificar o crear.

    Returns:
    tuple: Retorna un par (CustomerId, CustomerStatus) donde 'CustomerId' es el ID del cliente y 'CustomerStatus' es
           el estado del cliente ('New', 'Old', 'Otros').

    Ejemplo de uso:
    >>> cliente_titulo = "Ejemplo Cliente"
    >>> id_cliente, estado_cliente = clienteIDStatus(cliente_titulo)
    >>> print(id_cliente, estado_cliente)
    """
    respuesta1 = extraer_cliente_title(customer)
    if (respuesta1.status_code == 404):
        respuesta2 = crear_cliente(customer)
        # fichero = open("./"+customer+"/Datos Thingsboard "+customer+".txt", "w")
        fichero = open(f"deploy/{customer}/Datos Thingsboard {customer}.txt", "w")
        fichero.write(json.dumps(respuesta2.json()))
        fichero.close()
        CustomerId = respuesta2.json()["id"]["id"]
        CustomerStatus = "New"
    elif (respuesta1.status_code == 200):
        CustomerId = respuesta1.json()["id"]["id"]
        CustomerStatus = "Old"
    else:
        CustomerId = ""
        CustomerStatus = "Otros"
    return CustomerId, CustomerStatus


# Función que crear el RULE CHAIN DEVICE - TENANT ADMIN
def crear_RuleChain(ruleChainInfo):
    """
    Envía una solicitud POST para crear un nuevo RuleChain en ThingsBoard utilizando la información proporcionada en ruleChainInfo.

    Args:
    ruleChainInfo (dict): Un diccionario con la información necesaria para crear un RuleChain. Esto incluye nombres, tipos, y configuraciones específicas.

    Returns:
    response: Objeto de respuesta de la solicitud que incluye el estado y los datos devueltos por el servidor si la creación fue exitosa.
    None: Retorna None si ocurre un error en la conexión o durante la solicitud.

    Ejemplo de uso:
    >>> info_rulechain = {"name": "Nuevo RuleChain", "type": "CORE", "additionalInfo": "Información relevante"}
    >>> respuesta = crear_RuleChain(info_rulechain)
    >>> if respuesta and respuesta.status_code == 200:
    ...     print("RuleChain creado exitosamente.")
    ... else:
    ...     print("Error al crear el RuleChain.")
    """
    endpoint = f"{Root}/api/ruleChain"
    headers = {"Authorization": TOKEN, "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    data = json.dumps(ruleChainInfo)
    try:
        response = requests.post(endpoint, headers=headers, data=data)
        # print(response.json())
    except Error as err:
        print('La página no existe. Codigo: ' + str(err.code))
        print(err.headers)
        print(err.reason)
        # sys.exit()
        return None
    return response


# Función que actualiza el Metadata de la Rule Chain
def modificar_RuleChain(ruleChainMetadata):
    """
    Envía una solicitud POST para actualizar el metadata de un RuleChain existente en ThingsBoard utilizando la información proporcionada.

    Args:
    ruleChainMetadata (dict): Un diccionario con la metadata que se desea actualizar en el RuleChain, como configuraciones específicas.

    Returns:
    response: Objeto de respuesta de la solicitud que incluye el estado y los datos devueltos por el servidor si la actualización fue exitosa.
    None: Retorna None si ocurre un error en la conexión o durante la solicitud.

    Ejemplo de uso:
    >>> metadata_rulechain = {"additionalInfo": "Nueva información relevante"}
    >>> respuesta = modificar_RuleChain(metadata_rulechain)
    >>> if respuesta and respuesta.status_code == 200:
    ...     print("Metadata del RuleChain actualizado exitosamente.")
    ... else:
    ...     print("Error al actualizar el metadata del RuleChain.")
    """
    endpoint = f"{Root}/api/ruleChain/metadata"
    headers = {"Authorization": TOKEN, "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    data = json.dumps(ruleChainMetadata)
    try:
        response = requests.post(endpoint, headers=headers, data=data)
        # print(response.json())
    except Error as err:
        print('La página no existe. Codigo: ' + str(err.code))
        print(err.headers)
        print(err.reason)
        # sys.exit()
        return None
    return response


# Función para extraer Rule Chains por pagína y tamaño de página
def extraer_RuleChainsPage(pageSize, page):
    """
    Realiza una solicitud GET para obtener una lista de RuleChains de ThingsBoard paginada según los parámetros especificados.

    Args:
    pageSize (int): Número de RuleChains a retornar en una sola página.
    page (int): Número de la página de resultados a consultar.

    Returns:
    response: Objeto de respuesta de la solicitud que incluye el estado y los datos devueltos por el servidor si la consulta fue exitosa.
    None: Retorna None si ocurre un error en la conexión o durante la solicitud.

    Ejemplo de uso:
    >>> tamano_pagina = 10
    >>> numero_pagina = 1
    >>> respuesta = extraer_RuleChainsPage(tamano_pagina, numero_pagina)
    >>> if respuesta and respuesta.status_code == 200:
    ...     print("Consulta exitosa.")
    ... else:
    ...     print("Error en la consulta de RuleChains.")
    """
    # endpoint = Root+"/api/ruleChains?pageSize="+str(pageSize)+"&page="+str(page)
    endpoint = f"{Root}/api/ruleChains?pageSize={pageSize}&page={page}"
    headers = {"Authorization": TOKEN, "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    parametros = {"pageSize": pageSize, "page": page}
    try:
        response = requests.get(endpoint, headers=headers)  # , data=data)
        # print(response.json())
    except Error as err:
        print('La página no existe. Codigo: ' + str(err.code))
        print(err.headers)
        print(err.reason)
        # sys.exit()
        return None
    return response


# Función para extraer Todas las Rule Chains
def extraer_RuleChains(pageSize):
    """
    Obtiene todas las Rule Chains disponibles en ThingsBoard, paginando a través de todos los resultados disponibles.

    Args:
    pageSize (int): Número de RuleChains a retornar en cada página de la consulta.

    Returns:
    list: Una lista de todos los RuleChains recuperados, donde cada RuleChain es un diccionario con los detalles del mismo.

    Ejemplo de uso:
    >>> tamano_pagina = 10
    >>> todas_las_rulechains = extraer_RuleChains(tamano_pagina)
    >>> for rulechain in todas_las_rulechains:
    ...     print(rulechain)
    """
    page = 0
    response = extraer_RuleChainsPage(pageSize, page)
    responseJson = response.json()
    data = responseJson["data"]
    while (responseJson["hasNext"]):
        page = page + 1
        # print(page)
        response = extraer_RuleChainsPage(pageSize, page)
        responseJson = response.json()
        data = data + response.json()["data"]
    return data


# Función para extraer todas las Rule Chains por cliente
def extraer_RuleChainsCustomer(Customer, pageSize):
    """
    Filtra y recupera todas las Rule Chains asociadas con un cliente específico desde ThingsBoard.

    Args:
    Customer (str): El nombre del cliente utilizado para filtrar las Rule Chains.
    pageSize (int): Número de Rule Chains a retornar en cada página durante la recuperación inicial de todas las Rule Chains.

    Returns:
    list: Una lista de diccionarios, cada uno representando una Rule Chain que coincide con el nombre del cliente especificado.

    Ejemplo de uso:
    >>> cliente = "ClienteXYZ"
    >>> tamano_pagina = 10
    >>> rulechains_por_cliente = extraer_RuleChainsCustomer(cliente, tamano_pagina)
    >>> for rulechain in rulechains_por_cliente:
    ...     print(rulechain)
    """
    RuleChains = extraer_RuleChains(pageSize)
    data = []
    for i in range(len(RuleChains)):
        caso = RuleChains[i]
        if Customer in caso['name']:
            data = data + [caso]
    return data


# Función para extraer todas las Rule Chains por cliente y literal
def extraer_RuleChainsCustomerLiteral(Customer, pageSize, literal):
    """
    Filtra y recupera todas las Rule Chains que contienen tanto un nombre de cliente especificado como un literal adicional en su nombre desde ThingsBoard.

    Args:
    Customer (str): El nombre del cliente utilizado para filtrar las Rule Chains.
    pageSize (int): Número de Rule Chains a retornar en cada página durante la recuperación inicial de todas las Rule Chains.
    literal (str): Un literal adicional que debe estar presente en el nombre de las Rule Chains para que sean incluidas en el resultado.

    Returns:
    list: Una lista de diccionarios, cada uno representando una Rule Chain que coincide con los criterios especificados de nombre de cliente y literal.

    Ejemplo de uso:
    >>> cliente = "ClienteXYZ"
    >>> literal = "Sensor"
    >>> tamano_pagina = 10
    >>> rulechains_filtradas = extraer_RuleChainsCustomerLiteral(cliente, tamano_pagina, literal)
    >>> for rulechain in rulechains_filtradas:
    ...     print(rulechain)
    """
    RuleChains = extraer_RuleChains(pageSize)
    # data = []
    # for i in range(len(RuleChains)):
    #    caso = RuleChains[i]
    #    if (literal in caso['name']) & (Customer in caso['name']):
    #        data = data + [caso]
    data = [
        chain for chain in RuleChains
        if literal in chain['name'] and Customer in chain['name']
    ]
    return data


##  Extraer deviceRuleChainid, si no existe crea la RuleChain
def extraer_DevicesRuleChainId(customer, tipo):
    """
    Busca una Rule Chain específica por cliente y tipo. Si existe exactamente una, retorna su ID.
    Si no existe, crea una nueva usando una plantilla predefinida, modifica su metadata y retorna el nuevo ID.

    Args:
    customer (str): El nombre del cliente para buscar o crear la Rule Chain.
    tipo (str): El tipo de Rule Chain que define la plantilla a usar para su creación.

    Returns:
    str: El ID de la Rule Chain buscada o recién creada.
    None: Si no se encuentra exactamente una Rule Chain o si ocurre un error durante el proceso.

    Ejemplo de uso:
    >>> cliente = "ClienteXYZ"
    >>> tipo = "Device"
    >>> rule_chain_id = extraer_DevicesRuleChainId(cliente, tipo)
    >>> print(rule_chain_id)
    """
    RuleChainOld = extraer_RuleChainsCustomerLiteral(customer, PageSize, tipo)
    if len(RuleChainOld) == 1:
        return RuleChainOld[0]["id"]["id"]
    elif len(RuleChainOld) == 0:
        # Usar un diccionario para mapear tipos a ficheros ->¿Refactorizar a fichero con tipos y direcciones?
        TipoDeFichero = {
            "Device": "devices_root_rule_chain.json",
            "Buckets": "buckets_root_rule_chain.json",
            "Models": "models_root_rule_chain.json",
            "Estimaciones Modelo": "estimaciones_root_rule_chain.json",
            "Matriz Relacion": "matriz_root_rule_chain.json",
            "RAW": "raw_root_rule_chain.json",
            "Control": "default_root_rule_chain.json"
        }
        Fichero = TipoDeFichero.get(tipo)
        if not Fichero:
            Fichero = "default_root_rule_chain.json"

        with open(f'deploy/Plantillas/DeviceRuleChains/{Fichero}', 'r') as file:
            RuleChain = file.read().replace("XXXXXXXXXX", customer)
            if Fichero == "default_root_rule_chain.json":
                RuleChain = RuleChain.replace("ZZZZZZZZ", tipo)
            if Fichero == "devices_root_rule_chain.json":
                RuleChain = RuleChain.replace("ROOT_NODERED", root_nodered)
            if Fichero == "models_root_rule_chain.json":
                RuleChain = RuleChain.replace("ROOT_NODERED", root_nodered)
            if Fichero in ("devices_root_rule_chain.json", "models_root_rule_chain.json"):
                RuleChain = RuleChain.replace("ROOT_NODERED", root_nodered)
            if Fichero == "raw_root_rule_chain.json":
                RuleChain = RuleChain.replace("ROOT_NODERED", root_nodered)
                RuleChain = RuleChain.replace("previoXXXXXXXXXX", "previo" + customer)

        RuleChainInfo = json.loads(RuleChain)["ruleChain"]
        response = crear_RuleChain(RuleChainInfo)
        if not response or response.status_code != 200:
            print("Error al crear la Rule Chain")
            return None

        deviceRuleChainId = response.json()["id"]["id"]
        RuleChain = RuleChain.replace("YYYYYYYYYY", deviceRuleChainId)
        RuleChainMetadata = json.loads(RuleChain)["metadata"]
        modificar_RuleChain(RuleChainMetadata)
        return deviceRuleChainId
    else:
        print("Hay más de una Rule Chain asociada al cliente")
        return None


# Función que crear el DEVICE PROFILE
def crear_deviceProfile(deviceProfileInfo):
    """
    Envía una solicitud POST para crear un nuevo perfil de dispositivo en ThingsBoard utilizando la información proporcionada.

    Args:
    deviceProfileInfo (dict): Un diccionario que contiene la información necesaria para crear un perfil de dispositivo.

    Returns:
    response: Objeto de respuesta de la solicitud que incluye el estado y los datos devueltos por el servidor si la creación fue exitosa.
    None: Retorna None si ocurre un error en la conexión o durante la solicitud.

    Ejemplo de uso:
    >>> info_perfil = {"name": "Perfil de Dispositivo", "type": "default", "description": "Descripción del perfil"}
    >>> respuesta = crear_deviceProfile(info_perfil)
    >>> if respuesta and respuesta.status_code == 200:
    ...     print("Perfil de dispositivo creado exitosamente.")
    ... else:
    ...     print("Error al crear el perfil de dispositivo.")
    """
    endpoint = f'{Root}/api/deviceProfile'
    headers = {"Authorization": TOKEN, "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    data = json.dumps(deviceProfileInfo)
    try:
        response = requests.post(endpoint, headers=headers, data=data)
        # print(response.json())
    except Error as err:
        print('La página no existe. Codigo: ' + str(err.code))
        print(err.headers)
        print(err.reason)
        # sys.exit()
        return None
    return response


# Función que extrae los DEVICE PROFILES
def extraer_deviceProfiles(TOKEN):
    """
    Realiza una solicitud GET para recuperar todos los nombres de perfiles de dispositivos disponibles en ThingsBoard.

    Args:
    token (str): Token de autenticación necesario para acceder a la API de ThingsBoard.

    Returns:
    response: Objeto de respuesta de la solicitud que incluye el estado y los datos devueltos por el servidor si la consulta fue exitosa.
    None: Retorna None si ocurre un error en la conexión o durante la solicitud.

    Ejemplo de uso:
    >>> token = "SuTokenDeAcceso"
    >>> respuesta = extraer_deviceProfiles(token)
    >>> if respuesta and respuesta.status_code == 200:
    ...     print("Perfiles de dispositivo recuperados exitosamente.")
    ... else:
    ...     print("Error al recuperar los perfiles de dispositivo.")
    """
    endpoint = f"{Root}/api/deviceProfile/names"
    headers = {"Authorization": TOKEN, "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    try:
        response = requests.get(endpoint, headers=headers)
        # print(response.json())
    except Error as err:
        print('La página no existe. Codigo: ' + str(err.code))
        print(err.headers)
        print(err.reason)
        # sys.exit()
        return None
    return response


##  Extraer deviceProfileid, si no existe crea el Device Profile
def extraer_DevicesProfile(customer, tipo):
    """
    Busca un perfil de dispositivo específico por nombre, compuesto por el cliente y el tipo.
    Si no existe, crea uno nuevo usando una plantilla JSON correspondiente al tipo.

    Args:
    customer (str): El nombre del cliente utilizado para formar el nombre del perfil de dispositivo.
    tipo (str): El tipo de dispositivo que define la plantilla a usar para su creación.

    Returns:
    str: El ID del perfil de dispositivo buscado o recién creado.
    None: Si no se encuentra el perfil, se proporciona un tipo incorrecto, o si ocurre un error durante el proceso.

    Ejemplo de uso:
    >>> customer = "ClienteXYZ"
    >>> tipo = "Device"
    >>> profile_id = extraer_DevicesProfile(customer, tipo)
    >>> print(profile_id)
    """
    try:
        deviceProfiles = extraer_deviceProfiles(TOKEN).json()
        name = f"{customer} {tipo}"
        for Profile in deviceProfiles:
            if Profile['name'] == name:
                return Profile['id']['id']

        # Diccionario para mapear tipos a ficheros de plantillas
        TipoDeFichero = {
            "Device": "profile_device.json",
            "Buckets": "profile_buckets.json",
            "Models": "profile_models.json",
            "Estimaciones Modelo": "profile_estimaciones_modelo.json",
            "Matriz Relacion": "profile_matriz_relacion.json",
            "RAW": "profile_raw.json",
            "Control": "profile_control.json"
        }

        Fichero = TipoDeFichero.get(tipo)
        if not Fichero:
            Fichero = "profile_default.json"

        with open(f'deploy/Plantillas/DeviceProfiles/{Fichero}', 'r') as file:
            deviceProfile = file.read().replace("XXXXXXXXXX", customer)
            if Fichero == "profile_default.json":
                deviceProfile = deviceProfile.replace("ZZZZZZZZ", tipo)
            ruleChainId = extraer_DevicesRuleChainId(customer, tipo)
            if not ruleChainId:
                return None
            deviceProfile = deviceProfile.replace("YYYYYYYYYY", ruleChainId)
            deviceProfileInfo = json.loads(deviceProfile)

        response = crear_deviceProfile(deviceProfileInfo)
        if response and response.status_code == 200:
            return response.json()["id"]["id"]
        print("Error al crear el perfil de dispositivo")
    except Exception as e:
        print("Se produjo un error:", e)
        return None


# Función que crear el DEVICE PROFILE
def crear_device(name, tipo):
    """
    Crea un nuevo dispositivo en ThingsBoard utilizando un nombre y tipo proporcionados.

    Args:
    name (str): El nombre del dispositivo a crear.
    tipo (str): El tipo de dispositivo, utilizado para categorizar el dispositivo dentro de ThingsBoard.

    Returns:
    response: Objeto de respuesta de la solicitud que incluye el estado y los datos devueltos por el servidor si la creación fue exitosa.
    None: Retorna None si ocurre un error en la conexión o durante la solicitud.

    Ejemplo de uso:
    >>> nombre_dispositivo = "Sensor de Temperatura"
    >>> tipo_dispositivo = "Termómetro"
    >>> respuesta = crear_device(nombre_dispositivo, tipo_dispositivo)
    >>> if respuesta and respuesta.status_code == 200:
    ...     print("Dispositivo creado exitosamente.")
    ... else:
    ...     print("Error al crear el dispositivo.")
    """
    endpoint = f"{Root}/api/device"
    #print(f"endpoint: {endpoint}")
    headers = {"Authorization": TOKEN, "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    data = {"name": name, "type": tipo}
    data = json.dumps(data)
    #print(f"Headers: {headers}")
    #print(f"data: {data}")
    try:
        response = requests.post(endpoint, headers=headers, data=data)
        # print(response.json())
    except Error as err:
        print('La página no existe. Codigo: ' + str(err.code))
        print(err.headers)
        print(err.reason)
        # sys.exit()
        return None
    return response


# Función que crear el DEVICE PROFILE
def asignar_device_customer(deviceId, customerId):
    """
    Asigna un dispositivo existente a un cliente en ThingsBoard.

    Args:
    deviceId (str): El ID del dispositivo a asignar.
    customerId (str): El ID del cliente al que se asignará el dispositivo.

    Returns:
    response: Objeto de respuesta de la solicitud que incluye el estado y los datos devueltos por el servidor si la asignación fue exitosa.
    None: Retorna None si ocurre un error en la conexión o durante la solicitud.

    Ejemplo de uso:
    >>> id_dispositivo = "12345"
    >>> id_cliente = "67890"
    >>> respuesta = asignar_device_customer(id_dispositivo, id_cliente)
    >>> if respuesta and respuesta.status_code == 200:
    ...     print("Dispositivo asignado exitosamente al cliente.")
    ... else:
    ...     print("Error al asignar el dispositivo.")
    """
    # endpoint = Root+"/api/customer/"+str(customerId)+"/device/"+str(deviceId)
    endpoint = f"{Root}/api/customer/{str(customerId)}/device/{str(deviceId)}"
    headers = {"Authorization": TOKEN, "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    try:
        # print(customerId)
        # print(deviceId)
        response = requests.post(endpoint, headers=headers)  # , data=data)
        # print(response.json())
    except Error as err:
        print('La página no existe. Codigo: ' + str(err.code))
        print(err.headers)
        print(err.reason)
        # sys.exit()
        return None
    return response


# Función que devuelve los Ids de los dispositivos
def extract_id(deviceName):
    """
    Obtiene el ID de un dispositivo específico por su nombre desde ThingsBoard.

    Args:
    deviceName (str): El nombre del dispositivo cuyo ID se desea obtener.

    Returns:
    str: El ID del dispositivo si se encuentra.
    None: Retorna None si ocurre un error en la conexión, durante la solicitud, o si el dispositivo no existe.

    Ejemplo de uso:
    >>> nombre_dispositivo = "Sensor de Temperatura"
    >>> id_dispositivo = extract_id(nombre_dispositivo)
    >>> if id_dispositivo:
    ...     print(f"ID del dispositivo: {id_dispositivo}")
    ... else:
    ...     print("Dispositivo no encontrado o error en la solicitud.")
    """
    # endpoint = Root+"/api/tenant/devices?deviceName="+str(deviceName)
    endpoint = f"{Root}/api/tenant/devices?deviceName={str(deviceName)}"
    #print(f"endpoint for id: {endpoint}")
    headers = {"Authorization": TOKEN, "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    #print(f"TOKEN: {TOKEN}")
    try:
        response = requests.get(endpoint, headers=headers).json()
    except Error as err:
        print('La página no existe. Codigo: ' + str(err.code))
        print(err.headers)
        print(err.reason)
        # sys.exit()
        return None
    return response['id']['id']


# Función que devuelve las Credenciales de los dispositivos
def extract_Credentials(deviceId):
    """
    Obtiene las credenciales de un dispositivo específico en ThingsBoard utilizando su ID.

    Args:
    deviceId (str): El ID del dispositivo cuyas credenciales se desean obtener.

    Returns:
    str: El ID de las credenciales del dispositivo si se encuentra.
    None: Retorna None si ocurre un error en la conexión, durante la solicitud, o si las credenciales no existen.

    Ejemplo de uso:
    >>> id_dispositivo = "12345"
    >>> credenciales_id = extract_Credentials(id_dispositivo)
    >>> if credenciales_id:
    ...     print(f"ID de las credenciales del dispositivo: {credenciales_id}")
    ... else:
    ...     print("Credenciales no encontradas o error en la solicitud.")
    """
    endpoint = f"{Root}/api/device/{deviceId}/credentials"
    #print(f"endpoint for credential: {endpoint}")
    headers = {"Authorization": TOKEN, "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
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


def crear_devicesBulk(df):
    """
    Crea dispositivos en masa y asigna clientes a partir de un DataFrame. También extrae y asigna el ID y las credenciales de acceso.

    Args:
    df (pd.DataFrame): DataFrame que contiene los nombres y tipos de dispositivos a crear. Debe tener columnas 'name' y 'type'.

    Returns:
    pd.DataFrame: El mismo DataFrame de entrada pero con columnas adicionales 'devicesId' y 'accessToken' que contienen los IDs y tokens de acceso de los dispositivos creados.

    Ejemplo de uso:
    >>> df = pd.DataFrame({'name': ['Device1', 'Device2'], 'type': ['Type1', 'Type2']})
    >>> df_resultado = crear_devicesBulk(df)
    >>> print(df_resultado)
    """
    for i in range(df.shape[0]):
        response = crear_device(df["name"][i], df["type"][i])
        # print(response.status_code)
        # print(response.json())
        if (response.status_code == 200):
            asignar_device_customer(response.json()["id"]["id"], CustomerId)
    df['devicesId'] = [extract_id(deviceName) for deviceName in df['name']]
    df['accessToken'] = [extract_Credentials(deviceId) for deviceId in df['devicesId']]
    return df


def extract_telemetry(limit, deviceType, deviceID, keys, startTs=1000000000000, endTs=9999999999999, orderBy="DESC"):
    """
    Extrae datos de telemetría de un dispositivo a partir de sus claves (keys) dentro de un rango de tiempo específico.

    Args:
    limit (int): Número máximo de registros de telemetría a devolver.
    deviceType (str): Tipo de dispositivo (e.g., 'device', 'asset').
    deviceID (str): ID del dispositivo del que se extraerá la telemetría.
    keys (str): Claves de telemetría a extraer, separadas por comas.
    startTs (int, opcional): Timestamp inicial para filtrar la telemetría (por defecto 1000000000000).
    endTs (int, opcional): Timestamp final para filtrar la telemetría (por defecto 9999999999999).
    orderBy (str, opcional): Orden de los resultados, 'DESC' para descendente o 'ASC' para ascendente (por defecto 'DESC').

    Returns:
    dict: Respuesta en formato JSON con los datos de telemetría extraídos, o None si ocurre un error.

    Ejemplo de uso:
    >>> telemetry_data = extract_telemetry(limit=100, deviceType="device", deviceID="1234", keys="temperature,humidity")
    >>> print(telemetry_data)
    """
    params = {}
    params["keys"] = keys
    params["startTs"] = startTs
    params["endTs"] = endTs
    params["limit"] = limit
    params["orderBy"] = orderBy
    endpoint = f"{str(Root)}/api/plugins/telemetry/" + str(deviceType) + "/" + str(deviceID) + "/values/timeseries"
    headers = {"Authorization": TOKEN, "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    try:
        response = requests.get(endpoint, headers=headers, params=params).json()
    except Error as err:
        print('La página no existe. Codigo: ' + str(err.code))
        print(err.headers)
        print(err.reason)
        # sys.exit()
        return None
    return response


def post_data(data, endpoint):
    """
    Envía datos a un endpoint específico mediante una petición POST.

    Args:
    data (str): Datos en formato JSON que se enviarán en la petición POST.
    endpoint (str): URL del endpoint al cual se enviarán los datos.

    Returns:
    Response: Objeto de respuesta de la petición POST, o None si ocurre un error.

    Ejemplo de uso:
    >>> json_data = '{"key": "value"}'
    >>> response = post_data(json_data, "https://api.example.com/endpoint")
    >>> print(response.status_code)
    """
    headers = {"Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    try:
        response = requests.post(endpoint, headers=headers, data=data)
    except Error as err:
        print('La página no existe. Codigo: ' + str(err.code))
        print(err.headers)
        print(err.reason)
        return None
    return response


def post_nivel_crit(Cliente, Modelo, NumNivel, Cota, FechaInicio, FechaFin, Activo, accessToken):
    """
    Envía datos de nivel crítico de un cliente a un endpoint mediante una petición POST. Si el valor de 'Activo' es 1, 'FechaFin' no se envía.

    Args:
    Cliente (str): Nombre del cliente.
    Modelo (str): Modelo asociado al nivel crítico.
    NumNivel (int): Número de nivel.
    Cota (float): Valor de la cota asociada al nivel.
    FechaInicio (str): Fecha de inicio del nivel crítico en formato 'YYYY-MM-DD'.
    FechaFin (str, opcional): Fecha de fin del nivel crítico en formato 'YYYY-MM-DD'. No se envía si 'Activo' es 1.
    Activo (int): Indica si el nivel crítico está activo (1) o no (0).
    accessToken (str): Token de acceso para la autenticación.

    Returns:
    Response: Objeto de respuesta de la petición POST.

    Ejemplo de uso:
    >>> response = post_nivel_crit("Cliente1", "ModeloX", 3, 50.0, "2024-01-01", "2024-12-31", 1, "your_access_token")
    >>> print(response.status_code)
    """
    endpoint = f'{Root}/api/v1/{accessToken}/telemetry'
    # print(endpoint)
    if Activo == 1:
        data = f'{{"Cliente":"{Cliente}","Modelo":"{Modelo}","NumNivel":{str(NumNivel)},"Cota":{str(Cota)},"FechaInicio":"{FechaInicio}","FechaFin":null,"Activo":{str(Activo)}}}'
    else:
        data = f'{{"Cliente":"{Cliente}","Modelo":"{Modelo}","NumNivel":{str(NumNivel)},"Cota":{str(Cota)},"FechaInicio":"{FechaInicio}","FechaFin":"{FechaFin}","Activo":{str(Activo)}}}'
    response = post_data(data, endpoint)
    return response


def update_nivel_crit(Cliente, Modelo, NumNivel, Cota, FechaInicio, FechaFin, Activo, deviceId, timestamp):
    """
    Actualiza datos de nivel crítico de un dispositivo mediante una petición POST, incluyendo el timestamp. Si 'Activo' es 1, 'FechaFin' no se envía.

    Args:
    Cliente (str): Nombre del cliente.
    Modelo (str): Modelo asociado al nivel crítico.
    NumNivel (int): Número de nivel.
    Cota (float): Valor de la cota asociada al nivel.
    FechaInicio (str): Fecha de inicio del nivel crítico en formato 'YYYY-MM-DD'.
    FechaFin (str, opcional): Fecha de fin del nivel crítico en formato 'YYYY-MM-DD'. No se envía si 'Activo' es 1.
    Activo (int): Indica si el nivel crítico está activo (1) o no (0).
    deviceId (str): ID del dispositivo al cual se le actualizará la telemetría.
    timestamp (int): Timestamp que indica el momento de la actualización.

    Returns:
    Response: Objeto de respuesta de la petición POST, o None si ocurre un error.

    Ejemplo de uso:
    >>> response = update_nivel_crit("Cliente1", "ModeloX", 3, 50.0, "2024-01-01", "2024-12-31", 1, "deviceId123", 1672531199000)
    >>> print(response.status_code)
    """
    if Activo == 1:
        data = f'{{"ts":{timestamp},"values":{{"Cliente":"{Cliente}","Modelo":"{Modelo}","NumNivel":{str(NumNivel)},"Cota":{str(Cota)},"FechaInicio":"{FechaInicio}","FechaFin":null,"Activo":{str(Activo)}}}}}'
    else:
        data = f'{{"ts":{timestamp},"values":{{"Cliente":"{Cliente}","Modelo":"{Modelo}","NumNivel":{str(NumNivel)},"Cota":{str(Cota)},"FechaInicio":"{FechaInicio}","FechaFin":"{FechaFin}","Activo":{str(Activo)}}}}}'
    endpoint = f'{Root}/api/plugins/telemetry/DEVICE/{deviceId}/timeseries/any'
    # print(endpoint)
    headers = {"Authorization": TOKEN, "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json"}
    try:
        response = requests.post(endpoint, headers=headers, data=data)
    except Error as err:
        print('La página no existe. Codigo: ' + str(err.code))
        print(err.headers)
        print(err.reason)
        return None
    return response