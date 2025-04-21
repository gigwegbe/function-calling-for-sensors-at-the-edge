# thingsboard_utils.py
import requests
import json
from config import THINGSBOARD_URL, USERNAME, PASSWORD

def authenticate():
    """Authenticates with ThingsBoard and returns the JWT token."""
    auth_url = f"{THINGSBOARD_URL}/api/auth/login"
    payload = {'username': USERNAME, 'password': PASSWORD}
    response = requests.post(auth_url, json=payload)
    response.raise_for_status()
    return response.json()['token']

def get_device_id_by_name(device_name, token):
    """Retrieves the device ID from ThingsBoard based on the device name."""
    headers = {
        "Content-Type": "application/json",
        "X-Authorization": f"Bearer {token}"
    }
    url = f"{THINGSBOARD_URL}/api/tenant/devices?deviceName={device_name}"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    device = response.json()
    return device['id']['id'] if device else None

def get_device_keys(jwt_token, device_id):
    """Retrieves the timeseries keys for a specific device from ThingsBoard."""
    url = f"{THINGSBOARD_URL}/api/plugins/telemetry/DEVICE/{device_id}/keys/timeseries"
    headers = {
        "X-Authorization": f"Bearer {jwt_token}"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        return {
            "error": f"Failed to fetch keys: {response.status_code}",
            "details": response.text
        }