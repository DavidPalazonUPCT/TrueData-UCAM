import requests
import pandas as pd
import os

ROOT = os.getenv("ROOT", "http://localhost:9090")
USER = os.getenv("TB_USER", "tenant@thingsboard.org")
PASS = os.getenv("TB_PASS", "tenant")
CLIENT = os.getenv("CLIENT", "ESAMUR")

print(f"Conectando a {ROOT} con {USER}...")

# 1. Login
resp = requests.post(f"{ROOT}/api/auth/login",
    json={"username": USER, "password": PASS})

if resp.status_code != 200:
    print(f"ERROR: Login fallido ({resp.status_code}): {resp.text}")
    exit(1)

TOKEN = f"Bearer {resp.json()['token']}"
HEADERS = {"Authorization": TOKEN, "Content-Type": "application/json"}
print("Login OK.\n")

# 2. Leer lista de dispositivos del cliente
devices_path = f"src/data/{CLIENT}/DeviceImport.csv"
devices_df = pd.read_csv(devices_path)
print(f"Obteniendo tokens para {len(devices_df)} dispositivos de {CLIENT}...\n")

rows = []
for name in devices_df['name']:
    try:
        # Obtener ID del dispositivo
        r = requests.get(f"{ROOT}/api/tenant/devices?deviceName={name}", headers=HEADERS)
        if r.status_code != 200:
            print(f"  WARN: {name} no encontrado ({r.status_code})")
            continue
        device_id = r.json()['id']['id']

        # Obtener access token
        r2 = requests.get(f"{ROOT}/api/device/{device_id}/credentials", headers=HEADERS)
        access_token = r2.json().get('credentialsId')

        rows.append({
            'name': name,
            'type': f'{CLIENT} Device',
            'devicesId': device_id,
            'accessToken': access_token
        })
        print(f"  OK: {name} -> {access_token}")

    except Exception as e:
        print(f"  ERROR en {name}: {e}")

# 3. Guardar CSV actualizado
out_path = f"deploy/{CLIENT}/DeviceimportCredentials_{CLIENT}.csv"
df_out = pd.DataFrame(rows)
df_out.to_csv(out_path, index=False)
print(f"\n✅ Tokens actualizados en: {out_path} ({len(rows)}/{len(devices_df)} dispositivos)")
