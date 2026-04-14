"""
Lanza la simulación de inyección en PARALELO para múltiples dispositivos ThingsBoard.
Cada dispositivo se ejecuta en un hilo independiente con el mismo dataset ESAMUR.
"""

import pandas as pd
import requests
import time
import os
import argparse
import threading

ROOT = os.getenv("ROOT", "http://localhost:9090")
TB_USER = os.getenv("TB_USER", "tenant@thingsboard.org")
TB_PASS = os.getenv("TB_PASS", "tenant")

DEVICES = [
    "ESAMUR Model M3",
    "ESAMUR Estimaciones relativo M3",
    "ESAMUR Aggregation Mediana Ventana 1seg",   # nombre real encontrado
]


def get_token(device_name):
    """Login y obtener accessToken de un dispositivo."""
    resp = requests.post(f"{ROOT}/api/auth/login",
                         json={"username": TB_USER, "password": TB_PASS}, timeout=10)
    resp.raise_for_status()
    auth = f"Bearer {resp.json()['token']}"
    headers = {"Authorization": auth}

    r = requests.get(f"{ROOT}/api/tenant/devices?deviceName={device_name}",
                     headers=headers, timeout=10)
    if r.status_code == 404:
        raise Exception(f"Dispositivo '{device_name}' no encontrado (404)")
    r.raise_for_status()
    dev_id = r.json()['id']['id']

    r2 = requests.get(f"{ROOT}/api/device/{dev_id}/credentials", headers=headers, timeout=10)
    r2.raise_for_status()
    return r2.json()['credentialsId']


def worker(device_name, data_df, delay, stop_event):
    """Hilo de inyección para un dispositivo."""
    label = f"[{device_name}]"
    try:
        token = get_token(device_name)
        print(f"{label} ✅ Token: {token}")
    except Exception as e:
        print(f"{label} ❌ No se pudo obtener token: {e}")
        return

    url = f"{ROOT}/api/v1/{token}/telemetry"
    ok = err = 0

    for index, row in data_df.iterrows():
        if stop_event.is_set():
            break
        payload = {k: round(float(v), 4) for k, v in row.to_dict().items()}
        try:
            r = requests.post(url, json=payload, timeout=5)
            if r.status_code == 200:
                ok += 1
                print(f"{label} Fila {index+1} → OK")
            else:
                err += 1
                print(f"{label} Fila {index+1} → HTTP {r.status_code}")
        except Exception as e:
            err += 1
            print(f"{label} Fila {index+1} → EXCEPCIÓN: {e}")
        time.sleep(delay)

    print(f"\n{label} Completado. OK={ok} | Errores={err}")


def main(client, devices, delay, limit):
    data_path = f"src/data/{client}/data.csv"
    if not os.path.exists(data_path):
        print(f"ERROR: No se encontró {data_path}")
        return

    data_df = pd.read_csv(data_path)
    if limit:
        data_df = data_df.head(limit)

    print(f"{'='*60}")
    print(f"Servidor: {ROOT}")
    print(f"Cliente:  {client}")
    print(f"Filas:    {len(data_df)} | Delay: {delay}s")
    print(f"Devices:  {devices}")
    print(f"{'='*60}\n")

    # Obtener tokens antes de lanzar hilos
    print("Obteniendo tokens...")
    valid_devices = []
    for dev in devices:
        try:
            token = get_token(dev)
            valid_devices.append((dev, token))
            print(f"  ✅ {dev}: {token}")
        except Exception as e:
            print(f"  ❌ {dev}: {e}")

    if not valid_devices:
        print("\nNo se encontró ningún dispositivo válido. Abortando.")
        return

    print(f"\nLanzando {len(valid_devices)} hilos en paralelo...\n")
    stop_event = threading.Event()
    threads = []

    for dev_name, token in valid_devices:
        url = f"{ROOT}/api/v1/{token}/telemetry"
        t = threading.Thread(
            target=_send_worker,
            args=(dev_name, url, data_df, delay, stop_event),
            daemon=True
        )
        threads.append(t)
        t.start()

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\n\nInterrumpido. Deteniendo hilos...")
        stop_event.set()
        for t in threads:
            t.join(timeout=3)
        print("Hilos detenidos.")


def _send_worker(device_name, url, data_df, delay, stop_event):
    label = f"[{device_name:<40}]"
    ok = err = 0
    for index, row in data_df.iterrows():
        if stop_event.is_set():
            break
        payload = {k: round(float(v), 4) for k, v in row.to_dict().items()}
        try:
            r = requests.post(url, json=payload, timeout=5)
            if r.status_code == 200:
                ok += 1
                print(f"{label} Fila {index+1} → OK")
            else:
                err += 1
                print(f"{label} Fila {index+1} → HTTP {r.status_code}")
        except Exception as e:
            err += 1
            print(f"{label} Fila {index+1} → {e}")
        time.sleep(delay)
    print(f"\n{label} ✅ Fin. OK={ok} | Errores={err}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulador paralelo de inyección ThingsBoard")
    parser.add_argument("--client", type=str, default="ESAMUR")
    parser.add_argument("--devices", nargs="+", default=DEVICES,
                        help="Lista de nombres de dispositivos ThingsBoard")
    parser.add_argument("--delay", type=float, default=1.0, help="Segundos entre filas")
    parser.add_argument("--limit", type=int, default=None, help="Máximo de filas")
    args = parser.parse_args()

    main(client=args.client, devices=args.devices, delay=args.delay, limit=args.limit)
