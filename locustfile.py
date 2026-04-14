from locust import HttpUser, task, between
import os
import json
import random


class ThingsBoardUser(HttpUser):
    wait_time = between(1, 5)
    host = os.getenv("ROOT", "http://3.66.4.174:9090")

    def on_start(self):
        # 1. Autenticación
        self.token = self.authenticate()

        # 2. Obtener device ID y token
        self.device_name = "MCT Estimaciones relativo M2"  # Cambiar por tu dispositivo real
        self.device_id = self.get_device_id()
        self.device_token = self.get_device_credentials()
        self.device_keys = self.get_device_keys()

    def authenticate(self):
        # Cargar credenciales desde archivo (como en tu código original)
        with open('src/dataloader/Credenciales.txt') as f:
            credenciales = f.read().strip()

        response = self.client.post(
            "/api/auth/login",
            headers={"Content-Type": "application/json"},
            data=credenciales
        )
        return f"Bearer {response.json()['token']}"

    def get_device_id(self):
        # Obtener ID del dispositivo por nombre
        response = self.client.get(
            f"/api/tenant/devices?deviceName={self.device_name}",
            headers={"Authorization": self.token}
        )
        return response.json()['id']['id']

    def get_device_credentials(self):
        # Obtener token del dispositivo usando el ID
        response = self.client.get(
            f"/api/device/{self.device_id}/credentials",
            headers={"Authorization": self.token}
        )
        return response.json().get('credentialsId')

    def get_device_keys(self):
        endpoint = f"/api/plugins/telemetry/DEVICE/{self.device_id}/keys/timeseries"
        headers = {"Authorization": self.token, "Content-Type": "application/json;charset=UTF-8",
                   "Accept": "application/json"}
        keysList = self.client.get(endpoint, headers=headers).json()
        keysString = ','.join(keysList)
        return keysString

    @task(5)
    def get_telemetry(self):
        # Obtener datos de telemetría (ejemplo con 3 claves)
        keys = self.device_keys
        self.client.get(
            f"/api/plugins/telemetry/DEVICE/{self.device_id}/values/timeseries",
            params={"keys": keys, "limit": 100},
            headers={"Authorization": self.token},
            name="/api/telemetry"
        )

    #@task(3)
    #def send_telemetry(self):
        # Enviar datos de telemetría usando el device token
    #    payload = {
    #        "temperature": random.randint(20, 30),
    #        "humidity": random.randint(40, 80)
    #    }

    #    self.client.post(
    #        f"/api/v1/{self.device_token}/telemetry",
    #        json=payload,
    #        headers={"Authorization": self.token},
    #        name="/api/telemetry/post"
    #    )