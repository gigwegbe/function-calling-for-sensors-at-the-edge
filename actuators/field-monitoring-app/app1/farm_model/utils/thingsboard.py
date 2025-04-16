import os
import requests
import logging
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ThingsBoard settings
host = os.getenv('THINGSBOARD_HOST', 'localhost')
THINGSBOARD_URL = f"http://{host}:8080" if host == 'localhost' else f"http://{host}:9090"
USERNAME = "tenant@thingsboard.org"
PASSWORD = "tenant"

jwt_token = None

def get_jwt_token():
    """Authenticate with ThingsBoard and retrieve a JWT token."""
    global jwt_token
    if jwt_token:
        return jwt_token
    
    url = f"{THINGSBOARD_URL}/api/auth/login"
    payload = {"username": USERNAME, "password": PASSWORD}
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        logging.info("Authenticated successfully")
        jwt_token = response.json().get("token")
        return jwt_token
    else:
        logging.error("Failed to authenticate: %s", response.text)
        return None

def get_device_token(jwt_token, device_id):
    """Retrieve the device token for a given device ID."""
    headers = {"X-Authorization": f"Bearer {jwt_token}"}
    url = f"{THINGSBOARD_URL}/api/device/{device_id}/credentials"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("credentialsId")
    else:
        logging.error(f"Failed to retrieve device token: {response.text}")
        return None

def send_telemetry(device_token, telemetry_data):
    """Send telemetry data to ThingsBoard using the device token."""
    headers = {"Content-Type": "application/json"}
    url = f"{THINGSBOARD_URL}/api/v1/{device_token}/telemetry"
    response = requests.post(url, headers=headers, json=telemetry_data)
    print("[INFO]Response from Thingsboard:", response)
    if response.status_code != 200:
        logging.error(f"Failed to send telemetry data: {response.text}")
        return False
    return True

def create_or_update_device_on_thingsboard(jwt_token, device_data, device_type="actuator"):
    """Create or reuse a device on ThingsBoard."""
    url = f"{THINGSBOARD_URL}/api/device"
    headers = {
        "X-Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }

    # Check if a device with the given name already exists
    search_url = f"{THINGSBOARD_URL}/api/tenant/devices?deviceName={device_data['name']}"
    search_response = requests.get(search_url, headers=headers)
    if search_response.status_code == 200:
        existing_device = search_response.json()
        if existing_device and "id" in existing_device:
            logging.info(f"Device '{device_data['name']}' already exists on ThingsBoard. Reusing it.")
            return existing_device["id"]["id"]  # Return the existing device ID

    # Construct the payload for creating or updating the device
    payload = {
        "name": device_data["name"],
        "type": device_data["type"],
        "label": device_data.get("label", ""),
        "additionalInfo": device_data.get("additionalInfo", {}),
        "keys": device_data.get("keys", []),
    }

    # Optional fields for advanced device configuration
    if "deviceProfileId" in device_data:
        payload["deviceProfileId"] = device_data["deviceProfileId"]
    if "firmwareId" in device_data:
        payload["firmwareId"] = device_data["firmwareId"]
    if "softwareId" in device_data:
        payload["softwareId"] = device_data["softwareId"]
    if "deviceData" in device_data:
        payload["deviceData"] = device_data["deviceData"]

    # Create a new device on ThingsBoard
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        logging.info(f"{device_type.capitalize()} created successfully on ThingsBoard")
        return response.json().get("id").get("id")
    else:
        logging.error(f"Failed to create {device_type} on ThingsBoard: {response.text}")
        return None
    
def get_from_device(jwt_token, device_id, start_ts, end_ts, keys, limit, offset):
    """Get telemetry data from a device on ThingsBoard."""
    url = f"{THINGSBOARD_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
    params = {
        "keys": keys,
        "startTs": start_ts,
        "endTs": end_ts,
        "limit": limit,
        "offset": offset
    }
    headers = {"X-Authorization": f"Bearer {jwt_token}"}
    
    response = requests.get(url, headers=headers, params=params)
    return response.json() if response.status_code == 200 else {"error": "Failed to fetch telemetry data"}

def get_sensor_data(jwt_token, device_id, keys):
    """Retrieve the latest telemetry data for a given sensor."""
    end_ts = int(time.time() * 1000)
    start_ts = end_ts - (24 * 60 * 60 * 1000)
    limit = 1  # Fetch the latest data
    offset = 0  # No pagination

    data = get_from_device(jwt_token, device_id, start_ts, end_ts, keys, limit, offset)
    logging.debug(f"Retrieved sensor data: {data}")
    
    if data:
        # Extract the first value for each key
        parsed_data = {}
        for key in keys:
            if key in data and len(data[key]) > 0:
                parsed_data[key] = float(data[key][-1]["value"])  # Convert the value to float
            else:
                parsed_data[key] = None  # Handle missing data
        return parsed_data
    return None

    