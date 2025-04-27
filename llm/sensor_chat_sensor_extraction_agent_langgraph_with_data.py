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
import pytz

import plotly.graph_objects as go
from langchain_core.tools import tool
from plotly.subplots import make_subplots

# --- Configuration ---
THINGSBOARD_URL = "http://localhost:8080"
USERNAME = "tenant@thingsboard.org"
PASSWORD = "tenant"

# --- Load API Keys and Initialize Model ---
load_dotenv()
openai_api_key = os.getenv("OPENAI_PROJECT_API_KEY")
model = ChatOpenAI(api_key=openai_api_key, model="gpt-4o", temperature=0)

# --- Load Farm Data ---
def load_farm_data():
    with open("smaller_json.json") as f:
        farm_data = json.load(f)
    return json.dumps(farm_data["farm"]["fields"], indent=2)

farm_description = load_farm_data()

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
        "limit": 100,
        "agg": "NONE"
    }
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()

# --- Sensor Extraction Tooling ---
class SensorExtraction(BaseModel):
    sensor_id: List[str] = Field(..., description="List of sensor IDs relevant to the query")

def build_prompt_sensor(farm_description: str):
    system_message = SystemMessage(
        content=(
            "You are a smart farm assistant. Based on the user query and this farm data, extract sensor IDs.\n"
            "Respond ONLY with a JSON object in this format: {\"sensor_id\": [...]}\n\n"
            f"Farm field data:\n{farm_description}"
        )
    )
    human_message = HumanMessagePromptTemplate.from_template("{input}")
    return ChatPromptTemplate.from_messages([system_message, human_message])

def build_sensor_extraction_tool(model, prompt_template) -> Runnable:
    runnable = create_openai_fn_runnable([SensorExtraction], model, prompt_template)

    @tool
    def sensor_extraction(input: str) -> dict:
        """Extract relevant sensor IDs from a user query about farm fields."""
        return runnable.invoke({"input": input})

    return sensor_extraction

# --- Telemetry Fetching Tooling ---
class TelemetryRequest(BaseModel):
    device_names: List[str] = Field(..., description="List of device names to query telemetry for")
    keys: str = Field("temp,moisture_content,relative_humidity,soil_conductivity", description="Comma-separated telemetry keys to fetch (e.g., temp,humidity)")
    # hours: Optional[int] = Field(24, description="How many hours back to fetch data from")


def convert_timestamp_to_readable(ts, timezone="UTC"):
    # Convert milliseconds to seconds
    timestamp_in_seconds = ts / 1000
    # Convert to UTC datetime
    utc_time = datetime.utcfromtimestamp(timestamp_in_seconds)
    
    # Set the timezone to UTC
    utc_time = pytz.utc.localize(utc_time)
    
    kigali_tz = pytz.timezone('Africa/Kigali')
    # Convert to the desired timezone (e.g., Europe/Paris)
    local_time = utc_time.astimezone(kigali_tz)
    
    # Format the datetime to a readable string
    readable_time = local_time.strftime('%Y-%m-%d %H:%M:%S')
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
                end_ts=end_ts,
                interval=300000
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
prompt_template = build_prompt_sensor(farm_description)
sensor_tool = build_sensor_extraction_tool(model, prompt_template)
sensor_extraction_agent = create_react_agent(
    model=model,
    tools=[sensor_tool, fetch_sensor_telemetry],
    prompt="You are an expert in identifying relevant sensor IDs from natural language farm queries.",
    name="sensor_extraction_agent"
)

# def extract_time_series(data):
#     x = []
#     y = []
#     for point in data:
#         try:
#             ts = int(point.get("ts", 0))
#             val = float(point.get("value", 0))
#             x.append(datetime.fromtimestamp(ts / 1000))
#             y.append(val)
#         except (TypeError, ValueError, AttributeError):
#             continue
#     return x, y

# @tool
# def visualize_sensor_data(data: dict) -> str:
#     """
#     Visualizes telemetry data from multiple sensors over time.

#     Args:
#         data (dict): A nested dictionary of the form {sensor_id: {metric_name: [{"ts": ..., "value": ...}, ...]}}

#     Returns:
#         str: A message confirming that the visualization was created and saved as an HTML file.
#     """

# # Collect all traces
#     traces = []
#     for sensor_id, sensor_metrics in data.items():
#         for metric_name, readings in sensor_metrics.items():
#             x, y = extract_time_series(readings)
#             if x and y:
#                 trace_name = f"{sensor_id} - {metric_name}"
#                 traces.append(go.Scatter(x=x, y=y, mode='lines+markers', name=trace_name))

#         # Plot
#     fig = go.Figure(traces)
#     fig.update_layout(
#         title="Sensor Readings Over Time",
#         xaxis_title="Timestamp",
#         yaxis_title="Sensor Value",
#         template="plotly_dark"
#     )
#     fig.show()
#     # Plot
#     fig = go.Figure(traces)
#     fig.update_layout(
#         title="Sensor Readings Over Time",
#         xaxis_title="Timestamp",
#         yaxis_title="Sensor Value",
#         template="plotly_dark"
#     )
#     fig.show()
#     # Save the figure as an HTML file to display later
#     # fig.write_html("plot.html")
#     fig.write_image("plot.png")
    
#     return "Visualization created successfully. You can view it in the generated HTML file."

def extract_time_series(data):
    x = []
    y = []
    for point in data:
        try:
            ts = int(point.get("ts", 0))
            val = float(point.get("value", 0))
            x.append(datetime.fromtimestamp(ts / 1000))
            y.append(val)
        except (TypeError, ValueError, AttributeError):
            continue
    return x, y

# @tool
# def visualize_sensor_data(data: dict) -> str:
#     """
#     Visualizes telemetry data from multiple sensors over time.

#     Args:
#         data (dict): A nested dictionary of the form {sensor_id: {metric_name: [{"timestamp": ..., "value": ...}, ...]}}

#     Returns:
#         str: A message confirming that the visualization was created and saved as an HTML file.
#     """
#     # Create subplots dynamically based on the number of metrics
#     num_metrics = 0
#     for sensor_data in data.values():
#         num_metrics = max(num_metrics, len(sensor_data))

#     if num_metrics == 0:
#         return "No sensor data available for visualization."

#     fig = make_subplots(rows=num_metrics, cols=1, shared_xaxes=True, vertical_spacing=0.1)
#     row = 1
#     for sensor_id, sensor_metrics in data.items():
#         for i, (metric_name, readings) in enumerate(sensor_metrics.items()):
#             x = [datetime.strptime(reading['timestamp'], '%Y-%m-%d %H:%M:%S') for reading in readings]
#             y = [float(reading['value']) for reading in readings]
#             if x and y:
#                 trace = go.Scatter(x=x, y=y, mode='lines+markers', name=f"{sensor_id} - {metric_name}")
#                 fig.add_trace(trace, row=row, col=1)
#                 fig.update_yaxes(title_text=metric_name, row=row, col=1)
#                 row += 1

#     fig.update_layout(
#         title="Sensor Readings Over Time",
#         xaxis_title="Timestamp",
#         template="plotly_dark"
#     )
#     fig.show()

#     # Save the figure as an HTML file to display later
#     fig.write_image("plot.png")
    
#     return "Visualization created successfully. You can view it in the generated HTML file."

# def visualize_sensor_data(data: dict) -> str:
#     """
#     Visualizes telemetry data from multiple sensors over time.

#     Args:
#         data (dict): A nested dictionary of the form {sensor_id: {metric_name: [{"timestamp": ..., "value": ...}, ...]}}

#     Returns:
#         str: A message confirming that the visualization was created and saved as an HTML file.
#     """
#     # Create subplots dynamically based on the number of metrics
#     num_metrics = 0
#     for sensor_data in data.values():
#         num_metrics = max(num_metrics, len(sensor_data))

#     if num_metrics == 0:
#         return "No sensor data available for visualization."

#     fig = make_subplots(rows=num_metrics, cols=1, shared_xaxes=True, vertical_spacing=0.1)
#     row = 1
#     for sensor_id, sensor_metrics in data.items():
#         for i, (metric_name, readings) in enumerate(sensor_metrics.items()):
#             x = [datetime.strptime(reading['timestamp'], '%Y-%m-%d %H:%M:%S') for reading in readings]
#             y = [float(reading['value']) for reading in readings]
#             if x and y:
#                 trace = go.Scattergl(x=x, y=y, mode='lines+markers', name=f"{sensor_id} - {metric_name}")  # Use scattergl
#                 fig.add_trace(trace, row=row, col=1)
#                 fig.update_yaxes(title_text=metric_name, row=row, col=1)
#                 row += 1

#     fig.update_layout(
#         title="Sensor Readings Over Time",
#         xaxis_title="Timestamp",
#         template="plotly_dark"
#     )
#     fig.show()

#     # Save the figure as an image file (optional)
#     fig.write_image("plot.png")
    
#     return "Visualization created successfully. You can view it in the generated HTML file."


@tool
def visualize_sensor_data(data: dict) -> str:
    """
    Visualizes telemetry data from multiple sensors over time.

    Args:
        data (dict): A nested dictionary of the form {sensor_id: {metric_name: [{"timestamp": ..., "value": ...}, ...]}}

    Returns:
        str: A message confirming that the visualization was created and saved as an HTML file.
    """
    num_sensors = len(data)
    if num_sensors == 0:
        return "No sensor data available for visualization."

    fig = make_subplots(rows=num_sensors, cols=1, shared_xaxes=True, vertical_spacing=0.1)
    row = 1
    for sensor_id, sensor_metrics in data.items():
        for metric_name, readings in sensor_metrics.items():
            x = [datetime.strptime(reading['timestamp'], '%Y-%m-%d %H:%M:%S') for reading in readings]
            y = [float(reading['value']) for reading in readings]
            if x and y:
                trace = go.Scattergl(x=x, y=y, mode='lines+markers', name=f"{sensor_id} - {metric_name}")  # Use scattergl
                fig.add_trace(trace, row=row, col=1)
                fig.update_yaxes(title_text=f"{sensor_id} - {metric_name}", row=row, col=1) # More informative y-axis label
                break # Assuming only one metric per sensor for now, adjust if needed
        row += 1

    fig.update_layout(
        title="Sensor Readings Over Time",
        xaxis_title="Timestamp",
        template="plotly_dark"
    )
    fig.show()

    # Save the figure as an image file (optional)
    fig.write_image("plot.png")

    return "Visualization created successfully. You can view it in the generated HTML file."

sensor_visualization_agent = create_react_agent(
    model=model,
    tools=[sensor_tool, fetch_sensor_telemetry, visualize_sensor_data],  # Add the visualization tool
    prompt="You are an expert in visualizing sensor data from a smart farm. You can create time series charts data.",
    name="sensor_visualization_agent"
)


# # --- Example Usage ---
# input_query = "Get me temperature  plot  in north and central field."
# inputs = {"messages": [HumanMessage(content=input_query)]}
# result = sensor_visualization_agent.invoke(inputs)

# # Print result
# for msg in result["messages"]:
#     msg.pretty_print()