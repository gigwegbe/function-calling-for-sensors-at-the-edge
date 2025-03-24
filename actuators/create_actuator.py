import random
import requests
import json
import os
import time
import logging


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ThingsBoard settings
host = os.getenv('THINGSBOARD_HOST', 'localhost')
logging.info(f"ThingsBoard host: {host}")

THINGSBOARD_URL = f"http://{host}:8080" if host == 'localhost' else f"http://{host}:9090"

logging.info(f"ThingsBoard URL: {THINGSBOARD_URL}")

USERNAME = "tenant@thingsboard.org"
PASSWORD = "tenant"

jwt_token = None

def get_input_with_default(prompt, default, env_var_name):
    """Get input from environment variables or use the default value."""
    value = os.getenv(env_var_name)
    if value is not None:
        try:
            return float(value)
        except ValueError:
            logging.warning(f"Invalid value for {env_var_name}. Using default: {default}")
    logging.info(f"{prompt} Using default: {default}")
    return default

# Fetch telemetry data for a given device ID with pagination
def get_from_device(jwt_token, device_id, start_ts, end_ts, keys, limit, offset):
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

def get_pump_device_id(jwt_token):
    """Retrieve the device ID of the pump if it exists."""
    headers = {
        "X-Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }
    devices_url = f"{THINGSBOARD_URL}/api/tenant/devices?pageSize=100&page=0"
    devices_response = requests.get(devices_url, headers=headers)
    
    if devices_response.status_code == 200:
        devices = devices_response.json().get("data", [])
        for device in devices:
            if device["name"] == "Irrigation Pump":
                logging.info("Pump device already exists")
                return device["id"]["id"]
    logging.info("Pump device not found")
    return None

def create_pump_device(jwt_token):
    """Create a new pump device if it does not already exist."""
    device_id = get_pump_device_id(jwt_token)
    if device_id:
        return device_id
    
    url = f"{THINGSBOARD_URL}/api/device"
    headers = {
        "X-Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "name": "Irrigation Pump",
        "type": "pump",
        "label": "Field Irrigation Pump",
        "additionalInfo": {"description": "Pump actuator for field irrigation system"}
    }
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        logging.info("Pump device created successfully")
        return response.json().get("id").get("id")
    else:
        logging.error("Failed to create pump device: %s", response.text)
        return None

def get_device_token(jwt_token, device_id):
    """Retrieve the device token for a given device ID."""
    headers = {
        "X-Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }
    url = f"{THINGSBOARD_URL}/api/device/{device_id}/credentials"
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        device_token = response.json().get("credentialsId")
        logging.info(f"Retrieved device token: {device_token}")
        return device_token
    else:
        logging.error(f"Failed to retrieve device token: {response.text}")
        return None
    
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
# Ask the user for temperature and moisture thresholds
# def get_input_with_default(prompt, default):
#     user_input = input(f"{prompt} (default: {default}): ")
#     return float(user_input) if user_input.strip() else default

def monitor_and_control_pump(jwt_token, device_token, temperature_on_threshold=30, temperature_off_threshold=15, moisture_on_threshold=20, moisture_off_threshold=50):
    """Monitor sensor data from both sensors and control the pump based on threshold ranges."""
    pump_state = "OFF"  # Initial state of the pump
    
    # Get device IDs from environment variables or use defaults
    temperature_sensor_id = os.getenv("TEMPERATURE_SENSOR_ID", "7a3e0c90-082e-11f0-9195-432ae725fd12")
    moisture_sensor_id = os.getenv("MOISTURE_SENSOR_ID", "89bb59c0-082e-11f0-9195-432ae725fd12")
    send_on_off_telemetry(device_token, pump_state)  # Send initial state of the pump
    
    while True:
        # Fetch data from temperature_sensor
        temperature_data = get_sensor_data(jwt_token, temperature_sensor_id, ["temperature"])
        # Fetch data from soil_moisture_sensor
        moisture_data = get_sensor_data(jwt_token, moisture_sensor_id, ["soil_moisture"])

        # Check if data retrieval failed
        if not temperature_data or not moisture_data:
            time.sleep(10)  # Retry after 10 seconds
            continue

        temperature = temperature_data.get("temperature", 0)
        soil_moisture = moisture_data.get("soil_moisture", 0)

        logging.info(f"Temperature: {temperature}°C, Soil Moisture: {soil_moisture}%")

        # Determine whether to turn the pump ON or OFF based on thresholds
        if pump_state == "OFF" and (temperature > temperature_on_threshold or soil_moisture < moisture_on_threshold):
            logging.info("Conditions met. Turning pump ON.")
            send_on_off_telemetry(device_token, "ON")
            pump_state = "ON"
        elif pump_state == "ON" and (temperature < temperature_off_threshold and soil_moisture > moisture_off_threshold):
            logging.info("Conditions met. Turning pump OFF.")
            send_on_off_telemetry(device_token, "OFF")
            pump_state = "OFF"

        time.sleep(30)  # Check every 30 seconds


def send_telemetry(device_token, telemetry_data):
    """Send telemetry data to ThingsBoard using the device token."""
    headers = {
        "Content-Type": "application/json"
    }

    telemetry_payload = telemetry_data

    logging.debug(f"Sending telemetry payload: {telemetry_payload}")
    logging.info(f"Sending telemetry data to {THINGSBOARD_URL}...")
    url = f"{THINGSBOARD_URL}/api/v1/{device_token}/telemetry"
    telemetry_response = requests.post(
        url,
        headers=headers,
        json=telemetry_payload
    )

    if telemetry_response.status_code != 200:
        logging.error(f"Failed to send telemetry data: {telemetry_response.text}")
        return False

    logging.info("Telemetry data sent successfully")
    return True

def send_on_off_telemetry(device_token, state):
    """Send the pump's ON/OFF state as telemetry data."""
    binary_state = True if state == "ON" else False
    telemetry_data = {"state": binary_state}
    return send_telemetry(device_token, telemetry_data)

def test_send_on_off_telemetry(token):
    """Test sending ON/OFF telemetry data."""
    """Main function to authenticate, create device, and send telemetry."""

    if not token:
        return
    
    device_id = create_pump_device(token)
    logging.info(f"Device ID: {device_id}")
    if not device_id:
        return

    # Retrieve the device token dynamically
    device_token = get_device_token(token, device_id)
    if not device_token:
        return
    right_now = time.time()
    end_time = right_now + 3600  # Run for one hour
    while time.time() < end_time:
        # Send telemetry data
        logging.info("Sending telemetry data: Pump ON")
        send_on_off_telemetry(device_token, "ON")
        time.sleep(random.randint(5, 30))  # Random sleep between 5 to 30 seconds

        logging.info("Sending telemetry data: Pump OFF")
        send_on_off_telemetry(device_token, "OFF")
        time.sleep(random.randint(5, 30))  # Random sleep between 5 to 30 seconds


def test_monitor_and_control_pump(token):
    """Test monitoring and controlling the pump."""
    if not token:
        return
    
    device_id = create_pump_device(token)
    logging.info(f"Device ID: {device_id}")
    if not device_id:
        return

    # Retrieve the device token dynamically
    device_token = get_device_token(token, device_id)
    if not device_token:
        return

    # Get thresholds from environment variables or use defaults
    temperature_on_threshold = get_input_with_default(
        "Enter temperature ON threshold", 30.0, "TEMPERATURE_ON_THRESHOLD"
    )
    temperature_off_threshold = get_input_with_default(
        "Enter temperature OFF threshold", 15.0, "TEMPERATURE_OFF_THRESHOLD"
    )
    moisture_on_threshold = get_input_with_default(
        "Enter moisture ON threshold", 20.0, "MOISTURE_ON_THRESHOLD"
    )
    moisture_off_threshold = get_input_with_default(
        "Enter moisture OFF threshold", 50.0, "MOISTURE_OFF_THRESHOLD"
    )

    logging.info("Monitoring and controlling pump...")
    monitor_and_control_pump(
        token, device_token,
        temperature_on_threshold, temperature_off_threshold,
        moisture_on_threshold, moisture_off_threshold
    )
def main():
    token = get_jwt_token()
    if not token:
        return
    #test_send_on_off_telemetry(token)
    test_monitor_and_control_pump(token)


if __name__ == "__main__":
    main()