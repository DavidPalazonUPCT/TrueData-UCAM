import pandas as pd
import requests
import time
import os
import argparse

def get_token(root_url, device_name):
    """Login to ThingsBoard and get the access token for a device."""
    resp = requests.post(f"{root_url}/api/auth/login",
        json={"username": "tenant@thingsboard.org", "password": "tenant"}, timeout=10)
    if resp.status_code != 200:
        raise Exception(f"Login fallido: {resp.status_code}")
    auth = f"Bearer {resp.json()['token']}"
    headers = {"Authorization": auth}

    r = requests.get(f"{root_url}/api/tenant/devices?deviceName={device_name}", headers=headers, timeout=10)
    if r.status_code != 200:
        raise Exception(f"Dispositivo '{device_name}' no encontrado: {r.status_code}")
    dev_id = r.json()['id']['id']

    r2 = requests.get(f"{root_url}/api/device/{dev_id}/credentials", headers=headers, timeout=10)
    return r2.json()['credentialsId']


def simulate_ingestion(client, aggregation_device, delay=1, limit=None):
    root_url = os.getenv("ROOT", "http://localhost:9090")

    # --- 1. Obtener token del dispositivo de agregación ---
    print(f"Buscando token para '{aggregation_device}' en {root_url}...")
    try:
        token = get_token(root_url, aggregation_device)
        print(f"  Token encontrado: {token}")
    except Exception as e:
        print(f"  ERROR: {e}")
        print(f"\nIntentando leer token desde CSV de respaldo...")
        creds_path = f"deploy/{client}/DeviceimportCredentials_{client}.csv"
        if os.path.exists(creds_path):
            df = pd.read_csv(creds_path)
            match = df[df['name'] == aggregation_device]
            if not match.empty:
                token = match.iloc[0]['accessToken']
                print(f"  Token desde CSV: {token}")
            else:
                print(f"  ERROR: '{aggregation_device}' no está en el CSV. Abortando.")
                return
        else:
            print(f"  ERROR: CSV no encontrado en {creds_path}. Abortando.")
            return

    url = f"{root_url}/api/v1/{token}/telemetry"

    # --- 2. Cargar dataset ---
    data_path = f"src/data/{client}/data.csv"
    if not os.path.exists(data_path):
        print(f"ERROR: No se encontró {data_path}")
        return

    data_df = pd.read_csv(data_path)
    if limit:
        data_df = data_df.head(limit)

    print(f"\nIniciando simulación → '{aggregation_device}'")
    print(f"URL: {url}")
    print(f"Filas a enviar: {len(data_df)} | Delay: {delay}s\n")

    ok_count = 0
    err_count = 0

    for index, row in data_df.iterrows():
        # Payload completo: todos los sensores en un único POST
        payload = {k: round(float(v), 4) for k, v in row.to_dict().items()}

        print(f"[Fila {index+1}/{len(data_df)}] Enviando {len(payload)} sensores...")
        print(f"  Payload: {payload}")

        try:
            response = requests.post(url, json=payload, timeout=5)
            if response.status_code == 200:
                ok_count += 1
            else:
                err_count += 1
                print(f"  ERROR HTTP {response.status_code}: {response.text}")
        except Exception as e:
            err_count += 1
            print(f"  EXCEPCIÓN: {e}")

        time.sleep(delay)

    print(f"\n✅ Simulación completada. OK: {ok_count} | Errores: {err_count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulador de inyección de datos ESAMUR → ThingsBoard (Aggregation Device)")
    parser.add_argument("--client", type=str, default="ESAMUR", help="Nombre del cliente (ej: ESAMUR)")
    parser.add_argument("--device", type=str, default="ESAMUR Aggregation Mediana Ventana 1 seg",
                        help="Nombre del dispositivo de agregación en ThingsBoard")
    parser.add_argument("--delay", type=float, default=1.0, help="Segundos entre cada envío")
    parser.add_argument("--limit", type=int, default=None, help="Límite de filas a procesar")

    args = parser.parse_args()
    simulate_ingestion(client=args.client, aggregation_device=args.device,
                       delay=args.delay, limit=args.limit)
