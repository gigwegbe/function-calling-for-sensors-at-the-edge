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
    

@tool
def sensor_extraction(query: str) -> dict:
    """
    Extracts sensor telemetry from ThingsBoard based on user query.
    Supports field names (like 'North Field') and natural time ranges like 'yesterday'.
    """
    print("Received query:", query)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant that extracts sensor IDs from farm fields in the user's query. "
                "Return: {'sensors': ['TEMP-0100', 'TEMP-0200']} format. "
                "Field Mappings:\n"
                "- F001: North Field\n"
                "- F002: Northeast Field\n"
                "- F003: East Field\n"
                "- F004: Southeast Field\n"
                "- F005: South Field\n"
                "- F006: Southwest Field\n"
                "- F007: West Field\n"
                "- F008: Northwest Field\n"
                "- F009: Central Field\n"
            ),
        },
        {"role": "user", "content": query},
    ]

    # Call the LLM to extract fields/sensors
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages,
        tools=tools,
        tool_choice="auto",
    )

    response_message = response.choices[0].message
    
    if hasattr(response_message, 'tool_calls') and response_message.tool_calls:
        # This will hold all the tool responses we will generate
        tool_responses = []

        # Loop through each tool call that the LLM has requested
        for tool_call in response_message.tool_calls:
            # Extract the name of the function that the LLM wants to call
            function_name = tool_call.function.name
            
            # Look up the actual function object by name from the global scope
            function_to_call = globals().get(function_name)

            # Parse the arguments passed in the tool call (which come as a JSON string)
            function_args = json.loads(tool_call.function.arguments)

            # Call the actual function with the unpacked arguments
            function_response = function_to_call(**function_args)

            # Construct a tool response message so it can be appended to the conversation
            tool_responses.append({
                "tool_call_id": tool_call.id,   # Required for Chat API tracking
                "role": "tool",                 # Role must be 'tool' per OpenAI API
                "name": function_name,          # Name of the tool/function
                "content": function_response,   # Actual return value from the function
            })

        # Append the original assistant message that initiated the tool call
        messages.append(response_message)

        # Append all the tool responses (so the model gets context that the tools were called)
        messages.extend(tool_responses)

        # Send a second request to the model with the updated message list,
        # so it can now reason with the results of the tool calls
        second_response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,  # Now includes the tool responses
        )

        # After getting second_response
        response_content = second_response.choices[0].message.content

        try:
            sensors_response = json.loads(response_content)
        except json.JSONDecodeError:
            try:
                sensors_response = ast.literal_eval(response_content)
            except Exception as e:
                return {"error": f"Failed to parse LLM response: {str(e)}"}

        if not isinstance(sensors_response, dict) or "sensors" not in sensors_response:
            return {"error": "Invalid response format from LLM."}

        sensor_names = sensors_response["sensors"]

        # sensors_response = json.loads(second_response.choices[0].message.content)
        # sensor_names = sensors_response["sensors"]

        print("Raw LLM response:", second_response)

        results = {}

        for sensor_name in sensor_names:
            try:
                device_id = get_device_id_by_name(sensor_name, jwt_token)
                if not device_id:
                    results[sensor_name] = "Device not found"
                    continue

                keys = get_device_keys(jwt_token, device_id)
                if isinstance(keys, dict) and keys.get("error"):
                    results[sensor_name] = keys
                    continue

                # Get time range: default to last 24 hours
                end_ts = int(time.time() * 1000)
                start_ts = end_ts - (24 * 60 * 60 * 1000)

                data = get_historical_data(jwt_token, device_id, start_ts, end_ts, ",".join(keys))
                print(data)

                results[sensor_name] = {
                    "keys": keys,
                    "readings": data
                }

            except Exception as e:
                results[sensor_name] = {"error": str(e)}

        return results

    else:
        return {"error": "Sensor extraction failed"}
    


def run_alert_script():
    """
    Executes the external Python script 'my_script.py' using subprocess.

    Args:
        state (dict): Input state dictionary (unused in this function, but required for LangGraph compatibility).

    Returns:
        dict: A dictionary containing:
            - 'stdout': The standard output from the script, if it runs successfully.
            - 'stderr': The standard error from the script, if any.
            - 'error': The error message if the script fails to execute properly.
    """

    try:
        result = subprocess.run(
            ["python", "alert_script.py"],
            capture_output=True,
            text=True,
            check=True
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except subprocess.CalledProcessError as e:
        return {
            "error": e.stderr
        }


# Now create Alert Agent
alert_agent = create_react_agent(
    model,
    tools=[run_alert_script],
    prompt="You are a alert assistant, you create alert by running the `run_alert_script` function",
    name="alert_agent"

) 

# Similarly, create the sensor extraction agent with a name
sensor_extraction_agent = create_react_agent(
    model=model,
    tools=[sensor_extraction],
    prompt="You are an expert in extracting sensor data from user queries.",
    name="sensor_extraction_agent"
)

# Create the supervisor workflow
top_supervisor = create_supervisor(
    agents=[sensor_extraction_agent, alert_agent],
    model=model,
    prompt=(
        "You are a Farm Supervisor Agent. Your responsibilities include overseeing tasks related to sensor data retrieval and alert system. "
        "Delegate sensor-related queries to the sensor_extraction_agent, and alert related queries to the alert_agent"

    )
).compile(name="SCADAgric")


# Example input
input_query = "Create Alert."
# input_query = "Get the reading of temperature from the North field today."
inputs = {"messages": [HumanMessage(content=input_query)]}


result = top_supervisor.invoke(inputs)
result

for m in result['messages']:
    m.pretty_print()
     