import os
import requests
import json
from dotenv import load_dotenv
# from langchain_openai import ChatOpenAI
from langchain_community.utilities.sql_database import SQLDatabase
# from langchain_experimental.sql import SQLDatabaseSequentialChain
# from langchain_community.utilities.sql_database import SQLDatabase
from langchain_core.prompts import MessagesPlaceholder, ChatPromptTemplate
from langchain_core.prompts import PromptTemplate
from typing_extensions import Annotated, TypedDict
from langchain_community.tools.sql_database.tool import QuerySQLDataBaseTool
# from langchain_community.utilities.sql_database import SQLDatabase
from sqlalchemy import create_engine
from langgraph.prebuilt import create_react_agent
from langgraph_supervisor import create_supervisor
from langchain_openai import ChatOpenAI
# import psycopg2
import time 
import yaml
import json 
from langchain_community.agent_toolkits import JsonToolkit, create_json_agent
from langchain_community.tools.json.tool import JsonSpec
from langchain_openai import OpenAI
from langchain.tools import Tool



THINGSBOARD_URL = "http://localhost:8080"
USERNAME = "tenant@thingsboard.org"
PASSWORD = "tenant"
DASHBOARD_ID = "http://localhost:8080/tenants"

DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "thingsboard"
DB_USER = "thingsboard"
DB_PASSWORD = "postgres"


THINGSBOARD_HOST = "http://localhost:8080"
USERNAME = "tenant@thingsboard.org"
PASSWORD = "tenant"

# Authenticate and get the JWT token
auth_url = f'{THINGSBOARD_HOST}/api/auth/login'
auth_payload = {'username': USERNAME, 'password': PASSWORD}
auth_response = requests.post(auth_url, json=auth_payload)
auth_response.raise_for_status()
jwt_token = auth_response.json()['token']


# Load environment variables
load_dotenv()
openai_api_key = os.getenv('OPENAI_PROJECT_API_KEY')

# Load the device metadata
import json 
with open("/Users/george/Documents/final_push/function-calling-for-sensors-at-the-edge/farm_model_small_v2.json", "r") as file:
    data = json.load(file)

def get_farm_details(a: int) -> str:
    """Return Farm field details as a JSON string

    Args:
        a: Field Index
    """
    try:
        field_data = data['farm']['fields'][a]
        return json.dumps(field_data)
    except IndexError:
        return json.dumps({"error": f"Field index {a} is out of bounds."})
    except KeyError:
        return json.dumps({"error": "The 'farm' or 'fields' key was not found in the data."})
    except Exception as e:
        return json.dumps({"error": f"An error occurred: {e}"})
    

# create tool
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_farm_details",
            "description": "Return details about a specific farm field as a JSON object.",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {
                        "type": "integer",
                        "description": "The index of the field to retrieve details for (0-based).",
                    },
                },
                "required": ["a"],
            },
        },
    }
]

import openai 
client = openai.OpenAI(api_key=openai_api_key)
llm_model = "gpt-3.5-turbo"


def run_conversation(query):
    """Runs a conversation with the LLM that can call the get_farm_details tool."""
    messages = [
        {"role": "system", "content": "You are a helpful assistant that identifies relevant devices (sensor_list) mentioned in the user's request and returns them as a JSON array of their IDs e.g. If no specific devices are mentioned, return an empty JSON array."
        "F001 is North Field,"
        "F002 is Northeast Field"
        "F003 is East Field"
        "F004 is Southeast Field"
        "F005 is South Field"
        "F006 is Southwest Field"
        "F007 is West Field"
        "F008 is Northwest Field"
        "F009 is Central Field"
        "Note: if the right Field is not provided return an empty json"
        },
     
        {"role": "user", "content": query}
    ]

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages,
        tools=tools,
        tool_choice="auto", 
    )

    response_message = response.choices[0].message

    if response_message.tool_calls:
        print("LLM initiated a tool call:")
        print(response_message.tool_calls)

        tool_call = response_message.tool_calls[0]
        function_name = tool_call.function.name
        function_to_call = globals()[function_name]
        function_args = json.loads(tool_call.function.arguments)
        function_response = function_to_call(**function_args)

        print(f"Calling function '{function_name}' with arguments: {function_args}")
        print(f"Function returned: {function_response}")

        messages.append(response_message)
        messages.append(
            {
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": function_name,
                "content": function_response,
            }
        )
        second_response = client.chat.completions.create(
            # model="gpt-3.5-turbo-0613",
            model="gpt-3.5-turbo",
            messages=messages,
        )
        
        return second_response.choices[0].message.content
    else:
        # If no tool call, the LLM might be directly answering based on the system prompt
        try:
            # Attempt to parse the response as JSON (assuming it followed the system prompt)
            return json.loads(response_message.content)
        except (json.JSONDecodeError, TypeError):
            # If it's not valid JSON, return the raw content
            return response_message.content
        


user_query_farm = "Tell me the details of the sensors in the south  field."
response_farm = run_conversation(user_query_farm)
print(f"\nLLM Response about farm: {response_farm}")


sensor_ids = json.loads(response_farm)["sensor_list"]
sensor_ids


# 2. Get device ID by name
def get_device_id_by_name(device_name, token):
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
    url = f"{THINGSBOARD_URL}/api/plugins/telemetry/DEVICE/{device_id}/keys/timeseries"
    headers = {
        "X-Authorization": f"Bearer {jwt_token}"
    }

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()  # Returns a list of key names
    else:
        return {
            "error": f"Failed to fetch keys: {response.status_code}",
            "details": response.text
        }
    

# change the device name 
device_name = sensor_ids[0] #"HUM-0100"
sensor_id = get_device_id_by_name(device_name, jwt_token)
device_id = sensor_id
sensor_id


device_key = get_device_keys(jwt_token, sensor_id)
device_key = device_key[-1] # ['deviceId', 'unit', 'relative_humidity']
device_key 


# Last 24 hours timestamps
end_ts = int(time.time() * 1000)  
start_ts = end_ts - (340 * 60 * 60 * 1000)  # 24 hours ago

# keys = "temperature"  
keys = device_key


def get_historical_data(jwt_token, device_id, start_ts, end_ts, keys):
    url = f"{THINGSBOARD_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
    params = {"keys": keys, "startTs": start_ts, "endTs": end_ts, "limit": 100}
    headers = {"X-Authorization": f"Bearer {jwt_token}"}
    
    response = requests.get(url, headers=headers, params=params)
    return response.json() if response.status_code == 200 else {"error": "Failed to fetch telemetry data"}

response = get_historical_data(jwt_token, device_id, start_ts, end_ts, keys)
response