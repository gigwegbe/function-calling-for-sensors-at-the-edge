import os
import requests
import json
import time
from dotenv import load_dotenv
import openai

# Load environment variables
load_dotenv()
openai_api_key = os.getenv('OPENAI_PROJECT_API_KEY')

# Constants
THINGSBOARD_URL = "http://localhost:8080"
USERNAME = "tenant@thingsboard.org"
PASSWORD = "tenant"

# Authenticate and get the JWT token
def authenticate():
    auth_url = f'{THINGSBOARD_URL}/api/auth/login'
    auth_payload = {'username': USERNAME, 'password': PASSWORD}
    auth_response = requests.post(auth_url, json=auth_payload)
    auth_response.raise_for_status()
    return auth_response.json()['token']

jwt_token = authenticate()

# Load farm metadata
with open("/Users/george/Documents/final_push/function-calling-for-sensors-at-the-edge/farm_model_small_v2.json", "r") as file:
    farm_data = json.load(file)

# Helper function to get farm details
def get_farm_details(field_index: int) -> str:
    try:
        field_data = farm_data['farm']['fields'][field_index]
        return json.dumps(field_data)
    except IndexError:
        return json.dumps({"error": f"Field index {field_index} is out of bounds."})
    except KeyError:
        return json.dumps({"error": "The 'farm' or 'fields' key was not found in the data."})
    except Exception as e:
        return json.dumps({"error": f"An error occurred: {e}"})

# LLM setup
client = openai.OpenAI(api_key=openai_api_key)
llm_model = "gpt-3.5-turbo"

def run_conversation(query):
    """Runs a conversation with the LLM to retrieve sensor details."""
    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant that identifies relevant devices (sensor_list) mentioned in the user's "
                "request and returns them as a JSON array of their IDs. "
                "Field mappings: F001 is North Field, F002 is Northeast Field, F003 is East Field, "
                "F004 is Southeast Field, F005 is South Field, F006 is Southwest Field, "
                "F007 is West Field, F008 is Northwest Field, F009 is Central Field. "
                "If the right field is not provided, return an empty JSON array."
            ),
        },
        {"role": "user", "content": query},
    ]

    response = client.chat.completions.create(
        model=llm_model,
        messages=messages,
    )

    response_message = response.choices[0].message

    try:
        return json.loads(response_message.content)
    except (json.JSONDecodeError, TypeError):
        return {"error": "Invalid response from LLM", "content": response_message.content}

# ThingsBoard API helpers
def get_device_id_by_name(device_name, token):
    headers = {"Content-Type": "application/json", "X-Authorization": f"Bearer {token}"}
    url = f"{THINGSBOARD_URL}/api/tenant/devices?deviceName={device_name}"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    device = response.json()
    return device['id']['id'] if device else None

def get_device_keys(token, device_id):
    url = f"{THINGSBOARD_URL}/api/plugins/telemetry/DEVICE/{device_id}/keys/timeseries"
    headers = {"X-Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        return {"error": f"Failed to fetch keys: {response.status_code}", "details": response.text}

def get_historical_data(token, device_id, start_ts, end_ts, keys):
    url = f"{THINGSBOARD_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
    params = {"keys": keys, "startTs": start_ts, "endTs": end_ts, "limit": 100}
    headers = {"X-Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers, params=params)
    return response.json() if response.status_code == 200 else {"error": "Failed to fetch telemetry data"}

# Main function to get temperature for a specific field
def get_temperature_for_field(field_name):
    query = f"What is the temperature at {field_name}?"
    llm_response = run_conversation(query)

    if "sensor_list" not in llm_response or not llm_response["sensor_list"]:
        return {"error": "No sensors found for the specified field."}

    sensor_ids = llm_response["sensor_list"]
    device_name = sensor_ids[0]  # Assuming the first sensor is the one we need
    device_id = get_device_id_by_name(device_name, jwt_token)

    if not device_id:
        return {"error": f"Device ID not found for sensor {device_name}"}

    device_keys = get_device_keys(jwt_token, device_id)
    if "error" in device_keys:
        return device_keys

    temperature_key = "temperature" if "temperature" in device_keys else device_keys[-1]
    end_ts = int(time.time() * 1000)
    start_ts = end_ts - (24 * 60 * 60 * 1000)  # Last 24 hours

    historical_data = get_historical_data(jwt_token, device_id, start_ts, end_ts, temperature_key)
    return historical_data

# Example usage
field_name = "North Field"
temperature_data = get_temperature_for_field(field_name)
print(f"Temperature data for {field_name}: {temperature_data}")