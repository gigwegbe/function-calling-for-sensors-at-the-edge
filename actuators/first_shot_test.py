import requests
import json
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ThingsBoard settings
host = os.getenv('THINGSBOARD_HOST', 'localhost')
THINGSBOARD_URL = f"http://{host}:8080" if host == 'localhost' else f"http://{host}:9090"
USERNAME = "tenant@thingsboard.org"
PASSWORD = "tenant"

jwt_token = None

def get_jwt_token():
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

def upload_dashboard(jwt_token, dashboard_path):
    with open(dashboard_path, 'r') as file:
        dashboard_data = json.load(file)
    
    # Replace placeholder with the actual device ID
    device_id = get_pump_device_id(jwt_token)
    if not device_id:
        logging.error("Device ID not found. Cannot upload dashboard.")
        return
    
    dashboard_data['configuration']['entityAliases']['pump_device']['filter']['singleEntity']['id'] = device_id
    
    url = f"{THINGSBOARD_URL}/api/dashboard"
    headers = {
        "X-Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }
    response = requests.post(url, headers=headers, json=dashboard_data)
    if response.status_code == 200:
        logging.info("Dashboard uploaded successfully")
    else:
        logging.error("Failed to upload dashboard: %s", response.text)

def prepare_rule_chain_data(rule_chain_data, tenant_id):
    # Set tenant ID for the rule chain
    rule_chain_data['ruleChain']['tenantId'] = tenant_id
    
    # Replace IDs in rule nodes and connections
    for node in rule_chain_data['metadata']['nodes']:
        node['ruleChainId'] = None
        node['externalId'] = node.get('id')
        node['id'] = None
    
    if rule_chain_data['metadata'].get('ruleChainConnections'):
        for connection in rule_chain_data['metadata']['ruleChainConnections']:
            connection['targetRuleChainId'] = None  # Replace with actual logic to get internal ID
    
    return rule_chain_data

def upload_rule_chain(jwt_token, rule_chain_path):
    try:
        with open(rule_chain_path, 'r') as file:
            rule_chain_data = json.load(file)
            logging.debug(f"Loaded rule chain data: {json.dumps(rule_chain_data, indent=2)}")
    except FileNotFoundError:
        logging.error(f"Rule chain file not found: {rule_chain_path}")
        return
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from file {rule_chain_path}: {e}")
        return
    
    # Ensure the rule chain name is included in the payload
    if not rule_chain_data.get("ruleChain", {}).get("name"):
        logging.error("Rule chain name is missing in the JSON file.")
        return
    
    # Get tenant ID (replace with actual logic to fetch tenant ID)
    tenant_id = "5f19e850-f909-11ef-bcb0-4970cbae7421"
    
    # Preprocess the rule chain data
    rule_chain_data = prepare_rule_chain_data(rule_chain_data, tenant_id)
    
    url = f"{THINGSBOARD_URL}/api/ruleChain"
    headers = {
        "X-Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }
    
    # Log the payload being sent
    logging.debug(f"Rule chain payload: {json.dumps(rule_chain_data, indent=2)}")
    
    response = requests.post(url, headers=headers, json=rule_chain_data)
    if response.status_code == 200:
        logging.info("Rule chain uploaded successfully")
    else:
        logging.error(f"Failed to upload rule chain: {response.text}")

def control_pump(jwt_token, device_id, command):
    if command not in ["ON", "OFF"]:
        logging.warning("Invalid command. Use 'ON' or 'OFF'")
        return False
    
    headers = {
        "X-Authorization": f"Bearer {jwt_token}", 
        "Content-Type": "application/json"
    }
    
    telemetry_payload = {
        "green_indicator": command == "ON",
        "red_indicator": command == "OFF"
    }
    
    telemetry_response = requests.post(
        f"{THINGSBOARD_URL}/api/plugins/telemetry/DEVICE/{device_id}/SHARED_SCOPE",
        headers=headers,
        json=telemetry_payload
    )
    
    if telemetry_response.status_code != 200:
        logging.error("Failed to update LED indicators: %s", telemetry_response.text)
        return False
    
    attributes_payload = {
        "pump_status": command,
        "pump_speed": 100 if command == "ON" else 0
    }
    
    attribute_response = requests.post(
        f"{THINGSBOARD_URL}/api/plugins/telemetry/DEVICE/{device_id}/SHARED_SCOPE",
        headers=headers,
        json=attributes_payload
    )
    
    if attribute_response.status_code != 200:
        logging.error(f"Failed to send pump {command} command: %s", attribute_response.text)
        return False
    
    logging.info(f"Pump {command} command sent successfully")
    return True

def main():
    token = get_jwt_token()
    if not token:
        return
    
    device_id = create_pump_device(token)
    if not device_id:
        return

    # Upload dashboard and rule chain
    upload_dashboard(token, './Pump_widget.json')
    upload_rule_chain(token, './root_rule_chain.json')
    
    logging.info("Setup complete")

if __name__ == "__main__":
    main()