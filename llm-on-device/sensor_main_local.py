from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import Runnable
from langchain.chains.openai_functions import create_openai_fn_runnable
from pydantic import BaseModel, Field
from typing import List, Optional
import json
import os
import requests
from dotenv import load_dotenv
from langgraph.prebuilt import create_react_agent
from datetime import datetime, timedelta
from time import time
from langchain_ollama import ChatOllama


# --- Configuration ---
THINGSBOARD_URL = "http://localhost:8080"
USERNAME = "tenant@thingsboard.org"
PASSWORD = "tenant"

# --- Load API Keys and Initialize Model ---
load_dotenv()
# openai_api_key = os.getenv("OPENAI_PROJECT_API_KEY")
# model = ChatOpenAI(api_key=openai_api_key, model="gpt-4o", temperature=0)

model = ChatOllama(
    # model="llama3.2",
    # model="phi4-mini",
    # model="phi4-reasoning",
    model="granite3.1-moe:3b",
    keep_alive=-1,
    temperature=0,
    max_new_tokens=100
)

# --- Load Farm Data ---
def load_farm_data():
    with open("farm_model_smaller.json") as f:
        farm_data = json.load(f)
    return farm_data["farm"]["fields"]  # Load as Python object, not JSON string

farm_data = load_farm_data()  # Load the farm data

# --- ThingsBoard API Interactions ---
def get_jwt_token():
    url = f"{THINGSBOARD_URL}/api/auth/login"
    response = requests.post(url, json={"username": USERNAME, "password": PASSWORD})
    response.raise_for_status()
    return response.json()["token"]

def get_device_id_by_name(device_name, token):
    url = f"{THINGSBOARD_URL}/api/tenant/devices?deviceName={device_name}"
    headers = {"X-Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json().get("id", {}).get("id")

def fetch_telemetry(device_id, token, keys="temp,moisture_content,relative_humidity,soil_conductivity", start_ts=None, end_ts=None, interval=60000):
    url = f"{THINGSBOARD_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
    headers = {"X-Authorization": f"Bearer {token}"}
    params = {
        "keys": keys,
        "startTs": start_ts,
        "endTs": end_ts,
        "interval": interval,
        "limit": 1000,
        "agg": "NONE"
    }
    # response = requests.get(url=url, headers=headers, params=params)  # Corrected order
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()

# --- Sensor Extraction Tooling ---
class SensorExtraction(BaseModel):
    sensor_ids: List[str] = Field(..., description="List of sensor IDs relevant to the query")

def build_prompt_sensor():  # Remove farm_description from function argument
    system_message = SystemMessage(
        content=(
            "You are a smart farm assistant. Based on the user query and the provided farm data, extract the relevant sensor IDs.\n"
            "The farm data is a list of fields, where each field has a name and a sensor_list containing sensor types and their corresponding IDs.\n"
            "Respond ONLY with a JSON object in this format: {\"sensor_ids\": [\"sensor_id1\", \"sensor_id2\", ...]}\n"
            "IMPORTANT:  Do NOT invent sensor IDs.  Only use the sensor IDs provided in the farm data.\n"
            "Example Farm Data Structure:\n"
            "[\n"
            "  {\"F001\": {\"name\": \"North Field\", \"sensor_list\": {\"soil_temperature\": [\"TEMP-0100\"], \"field_air_humidity\": [\"HUM-0100\"]}}},\n"
            "  {\"F002\": {\"name\": \"Northeast Field\", \"sensor_list\": {\"soil_temperature\": [\"TEMP-0200\"], \"field_air_humidity\": [\"HUM-0200\"]}}}\n"
            "]\n"
        )
    )
    human_message = HumanMessagePromptTemplate.from_template("{input}")
    return ChatPromptTemplate.from_messages([system_message, human_message])


def build_sensor_extraction_tool(model, prompt_template, farm_data) -> Runnable:

    @tool
    def sensor_extraction(input: str) -> dict:
        """Extract relevant sensor IDs from a user query about farm fields."""
        formatted_prompt = prompt_template.format_messages(input=input)
        # Inject the farm data directly into the input
        full_input = formatted_prompt + [HumanMessage(content=f"Here is the farm data: {farm_data}")]
        response = model.invoke(full_input)
        
        try:
            # Try to extract JSON from the model's response
            start_idx = response.content.find("{")
            end_idx = response.content.rfind("}") + 1
            json_str = response.content[start_idx:end_idx]
            return json.loads(json_str)
        except Exception as e:
            return {"error": f"Failed to parse sensor IDs from response: {str(e)}", "raw": response.content}

    return sensor_extraction


# --- Telemetry Fetching Tooling ---
class TelemetryRequest(BaseModel):
    device_names: List[str] = Field(..., description="List of device names to query telemetry for")
    keys: str = Field("temp,moisture_content,relative_humidity,soil_conductivity", description="Comma-separated telemetry keys to fetch (e.g., temp,humidity)")
    # hours: Optional[int] = Field(24, description="How many hours back to fetch data from")

def convert_timestamp_to_readable(ts):
    # Convert milliseconds to seconds
    timestamp_in_seconds = ts / 1000
    # Convert to a readable datetime format
    readable_time = datetime.utcfromtimestamp(timestamp_in_seconds).strftime('%Y-%m-%d %H:%M:%S')
    return readable_time

@tool
def fetch_sensor_telemetry(input: TelemetryRequest) -> dict:
    """
    Fetch telemetry data for a list of device names and keys from ThingsBoard over the past N hours.
    """
    token = get_jwt_token()
    end_ts = int(time() * 1000)  # Current time in milliseconds
    start_ts = end_ts - 24 * 60 * 60 * 1000  # Last 24 hours

    all_data = {}

    for name in input.device_names:
        try:
            device_id = get_device_id_by_name(name, token)
            print(f"=============={device_id}===================")
            print(f"Fetching telemetry for device {name} with ID {device_id}")
            data = fetch_telemetry(
                device_id,
                token,
                keys=input.keys,
                start_ts=start_ts,
                end_ts=end_ts
            )
            print(f"Raw data for {name}: {data}")  # Log raw data to debug

            # Process raw data and convert timestamps to readable format
            processed_data = {}
            for key, values in data.items():
                processed_data[key] = []
                for reading in values:
                    timestamp = reading['ts']  # Access 'ts' field from reading
                    value = reading['value']   # Access 'value' field

                    # Convert the timestamp to a readable format
                    readable_time = convert_timestamp_to_readable(timestamp)

                    processed_data[key].append({
                        "timestamp": readable_time,
                        "value": value
                    })

            all_data[name] = processed_data

        except Exception as e:
            all_data[name] = {"error": str(e)}
            print(f"Error fetching telemetry for {name}: {e}")

    return all_data

# --- Initialize Langchain Agent ---
prompt_template = build_prompt_sensor()  #  Don't pass farm_description here
sensor_tool = build_sensor_extraction_tool(model, prompt_template, farm_data)
sensor_extraction_agent = create_react_agent(
    model=model,
    tools=[sensor_tool, fetch_sensor_telemetry],
    name="sensor_extraction_agent",
    prompt=(
        "You are a smart assistant for managing a precision agriculture system. "
        "Your task is to analyze the user's natural language query and use the appropriate tools to:\n\n"
        "1. Identify and extract the correct sensor IDs from the farm data using the `sensor_extraction` tool. "
        "These sensor IDs must match exactly with those provided in the farm data. Do not generate or hallucinate new sensor IDs.\n\n"
        "2. If the user also requests data or readings, use the `fetch_sensor_telemetry` tool with the extracted device names to retrieve telemetry.\n\n"
        "Always use the tools provided to extract sensor IDs and telemetry. "
        "Your response should rely strictly on the tools' outputs.\n\n"
        "Use structured reasoning if necessary, and be concise and accurate when calling tools."
    )
)

# sensor_extraction_agent = create_react_agent(
#     model=model,
#     tools=[sensor_tool, fetch_sensor_telemetry],
#     prompt="You are an expert in identifying relevant sensor IDs from natural language farm queries. Use the provided farm data to accurately extract sensor IDs.",
#     name="sensor_extraction_agent"
# )

# sensor_tool = build_sensor_extraction_tool(model, prompt_template)
# sensor_extraction_agent = create_react_agent(
#     model=model,
#     tools=[sensor_tool, fetch_sensor_telemetry],
#     prompt="You are an expert in identifying relevant sensor IDs from natural language farm queries.  Use the provided farm data to accurately extract sensor IDs.",
#     name="sensor_extraction_agent"
# )

# --- Example Usage ---
# input_query = "Get me soil conductivity of all field."
# input_query = "Get me soil conductivity of south, east and northern field."
# inputs = {"messages": [HumanMessage(content=input_query),
#             HumanMessage(content=f"Here is the farm data: {farm_data}")  # Inject farm data
#            ]}
# result = sensor_extraction_agent.invoke(inputs)

# # Print result
# for msg in result["messages"]:
#     msg.pretty_print()