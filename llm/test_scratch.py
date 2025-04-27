import dateparser
import ast
from datetime import datetime
import requests
import os
import json
import pandas as pd
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
import chainlit as cl
from langchain_core.prompts import MessagesPlaceholder, ChatPromptTemplate
from langchain.agents.format_scratchpad.openai_tools import format_to_openai_tool_messages
from langchain.agents.output_parsers.openai_tools import OpenAIToolsAgentOutputParser
from langchain.agents import AgentExecutor
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
import os
from datetime import datetime
import plotly.express as px
# from langchain_experimental.sql import SQLDatabaseSequentialChain
from langchain_community.utilities.sql_database import SQLDatabase
# from langchain_experimental.sql import SQLDatabaseChain
from langchain.schema.runnable.config import RunnableConfig
from langchain_core.messages import HumanMessage
import chainlit as cl
os.environ['MPLCONFIGDIR'] = '/Users/george/.config/matplotlib'
import matplotlib.pyplot as plt
from langchain_core.prompts import MessagesPlaceholder, ChatPromptTemplate
from langchain_core.prompts import PromptTemplate
from typing_extensions import Annotated, TypedDict
from langgraph.prebuilt import create_react_agent
from langgraph_supervisor import create_supervisor
from langchain_openai import ChatOpenAI
from langchain_community.agent_toolkits import JsonToolkit, create_json_agent
from langchain_community.tools.json.tool import JsonSpec
from langchain_openai import OpenAI
from langchain.tools import Tool
import openai 
from langchain.tools import tool
from datetime import datetime
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import AnyMessage, add_messages
from langgraph.graph import StateGraph
from langgraph.graph import StateGraph, END
import subprocess
import time 
from langchain_core.messages import HumanMessage

# from langchain.cache import InMemoryCache
# from langchain.globals import set_llm_cache
# set_llm_cache(InMemoryCache())

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

load_dotenv()
openai_api_key = os.getenv('OPENAI_PROJECT_API_KEY')
open_weather_api = os.getenv('OPENWEATHERMAP_API_KEY')
# OPENAI_API_KEY = os.getenv('OPENAI_PROJECT_API_KEY')
# llm_model = "gpt-3.5-turbo"
client = openai.OpenAI(api_key=openai_api_key)
# client = ChatOpenAI(api_key=openai_api_key, model="gpt-4o")
# model = ChatOpenAI(api_key=openai_api_key, model="gpt-4o")
model = ChatOpenAI(api_key=openai_api_key, model="gpt-4o")

# Authenticate with ThingsBoard
def authenticate():
    auth_url = f"{THINGSBOARD_URL}/api/auth/login"
    payload = {'username': USERNAME, 'password': PASSWORD}
    response = requests.post(auth_url, json=payload)
    response.raise_for_status()
    return response.json()['token']

jwt_token = authenticate()

# Load the device metadata
import json 
with open("/Users/george/Documents/final_push/function-calling-for-sensors-at-the-edge/farm_model_small_v2.json", "r") as file:
    data = json.load(file)



def get_historical_data(jwt_token, device_id, start_ts, end_ts, keys):
    url = f"{THINGSBOARD_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
    params = {"keys": keys, "startTs": start_ts, "endTs": end_ts, "limit": 100}
    headers = {"X-Authorization": f"Bearer {jwt_token}"}
    
    response = requests.get(url, headers=headers, params=params)
    return response.json() if response.status_code == 200 else {"error": "Failed to fetch telemetry data"}


# Define your tool for OpenAI function calling
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
                        "description": "The index of the field to retrieve details for (0-based)."
                    }
                },
                "required": ["a"]  # This should be a list of strings (you had an unquoted variable `a`)
            }
        }
    }
]

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
    

# @tool
# def sensor_extraction(query: str) -> dict:
#     """
#     Extracts sensor telemetry from ThingsBoard based on user query.
#     Supports field names (like 'North Field') and natural time ranges like 'yesterday'.
#     """
#     print("Received query:", query)

#     messages = [
#         {
#             "role": "system",
#             "content": (
#                 "You are a helpful assistant that extracts sensor IDs from farm fields in the user's query. "
#                 "Return: {'sensors': ['TEMP-0100', 'TEMP-0200']} format. "
#                 "Field Mappings:\n"
#                 "- F001: North Field\n"
#                 "- F002: Northeast Field\n"
#                 "- F003: East Field\n"
#                 "- F004: Southeast Field\n"
#                 "- F005: South Field\n"
#                 "- F006: Southwest Field\n"
#                 "- F007: West Field\n"
#                 "- F008: Northwest Field\n"
#                 "- F009: Central Field\n"
#             ),
#         },
#         {"role": "user", "content": query},
#     ]

#     # Call the LLM to extract fields/sensors
#     response = client.chat.completions.create(
#         model="gpt-3.5-turbo",
#         messages=messages,
#         tools=tools,
#         tool_choice="auto",
#     )

    # response_message = response.choices[0].message
    # print("Raw LLM response:", response_message)
    # return response_message

# @tool
# def sensor_extraction(query: str) -> dict:
#     """
#     Uses LLM to extract relevant sensor IDs from a natural language query.
#     Filters the extracted sensors to include only those matching relevant telemetry keys.
#     """
#     print("Received query:", query)

#     messages = [
#         {
#             "role": "system",
#             "content": (
#                 "You are a helpful assistant that extracts sensor IDs from farm fields in the user's query. "
#                 "You have access to a JSON model of the farm. Only extract sensor IDs.\n\n"
#                 "Return format: {'sensors': ['TEMP-0100', 'MC-0101']}\n\n"
#                 "Field mappings:\n"
#                 "- F001: North Field\n"
#                 "- F002: Northeast Field\n"
#                 "- F003: East Field\n"
#                 "- F004: Southeast Field\n"
#                 "- F005: South Field\n"
#                 "- F006: Southwest Field\n"
#                 "- F007: West Field\n"
#                 "- F008: Northwest Field\n"
#                 "- F009: Central Field\n"
#             )
#         },
#         {"role": "user", "content": query},
#     ]

#     response = client.chat.completions.create(
#         model="gpt-4o",
#         messages=messages,
#         tools=tools,
#         tool_choice="auto",
#     )

#     response_message = response.choices[0].message
#     print("Raw LLM message:", response_message)

#     # Try to parse and filter LLM response
#     try:
#         extracted = json.loads(response_message.tool_calls[0].function.arguments)
#         all_sensor_ids = extracted.get("sensors", [])
#     except Exception as e:
#         print("Failed to parse LLM output:", e)
#         return {"sensors": []}

#     # Validate and filter using farm data
#     allowed_keys = {"temp", "moisture_content", "relative_humidity", "soil_conductivity"}
#     valid_sensor_ids = []

#     for field in data["farm"]["fields"]:
#         for sensor in field["sensors"]:
#             if sensor["sensor_id"] in all_sensor_ids and sensor.get("type") in allowed_keys:
#                 valid_sensor_ids.append(sensor["sensor_id"])

#     print("Raw LLM response:", valid_sensor_ids)
#     return {"sensors": valid_sensor_ids}

from langchain.tools import tool
from typing import List
import pydantic
class SensorExtractionInput(pydantic.BaseModel):
    query: str

@tool(args_schema=SensorExtractionInput)
def sensor_extraction(query: str) -> dict:
    """
    Uses LLM to extract relevant sensor IDs from a natural language query.
    Filters to include only: temp, moisture_content, relative_humidity, soil_conductivity.
    """
    print("Received query:", query)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant that extracts sensor IDs from a user's farm query. "
                "You have access to a JSON model of the farm. Only extract sensor IDs.\n\n"
                "Return format: {'sensors': ['TEMP-0500', 'MC-0501']}\n\n"
                "Field mappings:\n"
                "- F001: North Field\n"
                "- F002: Northeast Field\n"
                "- F003: East Field\n"
                "- F004: Southeast Field\n"
                "- F005: South Field\n"
                "- F006: Southwest Field\n"
                "- F007: West Field\n"
                "- F008: Northwest Field\n"
                "- F009: Central Field\n"
            )
        },
        {"role": "user", "content": query},
    ]

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=tools,
        tool_choice="auto",
    )


    response_message = response.choices[0].message
    print("Raw LLM message:", response_message)

    # Try to parse the tool call arguments safely
    try:
        if hasattr(response_message, "tool_calls") and response_message.tool_calls:
            tool_args = response_message.tool_calls[0].function.arguments
            extracted = json.loads(tool_args) if isinstance(tool_args, str) else tool_args
            all_sensor_ids = extracted.get("sensors", [])
        else:
            print("No tool call found.")
            return {"sensors": []}
    except Exception as e:
        print("Failed to parse tool call:", e)
        return {"sensors": []}

    # Validate and filter against allowed sensor types
    allowed_keys = {"temp", "moisture_content", "relative_humidity", "soil_conductivity"}
    valid_sensor_ids = []

    for field in data["farm"]["fields"]:
        for sensor in field.get("sensors", []):
            if sensor["sensor_id"] in all_sensor_ids and sensor.get("type") in allowed_keys:
                valid_sensor_ids.append(sensor["sensor_id"])

    return {"sensors": valid_sensor_ids}


# # Example input
input_query = "Get the reading of temperature from the south field today."
inputs = {"messages": [HumanMessage(content=input_query)]}


# Similarly, create the sensor extraction agent with a name
sensor_extraction_agent = create_react_agent(
    model=model,
    tools=[sensor_extraction],
    prompt="You are an expert in extracting sensor data from user queries.",
    name="sensor_extraction_agent"
)


result = sensor_extraction_agent.invoke(inputs)
result

for m in result['messages']:
    m.pretty_print()
    


// {
//     "dockerfile_lines": [],
//     "graphs": {
//         "simple_supervisor": "./simple_supervisor.py:graph",
//         "sensor_network": "./sensor_network.py:graph",
//         "farm_supervisor": "./farm_supervisor.py:graph",
//         "farm_sensor_extraction_agent": "./sensor_chat_sensor_extraction_agent_langgraph.py:sensor_extraction_agent",
//         "sensor_chat_sensor_visualization_agent_langgraph": "./sensor_chat_sensor_visualization_agent_langgraph.py:sensor_visualization_agent",
//         "sensor_chat_sensor_main_supervisor": "./sensor_chat_sensor_main_supervisor_langgraph.py:top_supervisor",
//         "super_agent": "./sensor_chat_sensor_main_supervisor_langgraph_with_alert_and_control_with_receiver_chainlit.py:top_supervisor"
//     },
//     "env": "./.env",
//     "python_version": "3.11",
//     "dependencies": [
//         "."
//     ]
// }