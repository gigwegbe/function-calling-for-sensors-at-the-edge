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
from langgraph_supervisor import create_supervisor
import chainlit as cl
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

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


# --- Initialize Langchain Agent ---
prompt_template = build_prompt_sensor(farm_description)
sensor_tool = build_sensor_extraction_tool(model, prompt_template)
sensor_extraction_agent = create_react_agent(
    model=model,
    tools=[sensor_tool, fetch_sensor_telemetry],
    prompt="You are an expert in identifying relevant sensor IDs from natural language farm queries.",
    name="sensor_extraction_agent"
)


sensor_visualization_agent = create_react_agent(
    model=model,
    tools=[sensor_tool, fetch_sensor_telemetry, visualize_sensor_data],  # Add the visualization tool
    prompt="You are an expert in visualizing sensor data from a smart farm. You can create time series charts and other visualizations based on the data.",
    name="sensor_visualization_agent"
)


# Create the supervisor workflow
from langgraph.graph import Graph

# Create the supervisor prompt
supervisor_prompt = ChatPromptTemplate.from_messages([
    SystemMessage(
        "You are a Farm Supervisor Agent responsible for managing specialized agents that handle smart farm queries. "
        "Your goal is to analyze the user's request and decide which of the available agents is best suited to handle it.\n\n"
        "Here are the available agents and their purposes:\n"
        "- `sensor_extraction_agent`: Use this agent when the user is asking to identify specific sensors or retrieve raw data readings from sensors (e.g., 'What is the temperature of sensor A?', 'Get the moisture levels for field B').\n"
        "- `sensor_visualization_agent`: Use this agent when the user wants to see visual representations of sensor data over time (e.g., 'Show me a graph of temperature in the north field.', 'Visualize the humidity trends for all sensors.').\n\n"
        "Based on the user's request, you MUST respond with the exact name of the agent that should handle the query. "
        "Your response should be ONLY one of the following: 'sensor_extraction_agent' or 'sensor_visualization_agent'. "
        "Do not include any other text or explanations in your response."
    ),
    HumanMessage("{input}")
])

def log_intermediate(output):
    print(f"Intermediate Supervisor Output: {output}")
    return output

# Create the supervisor chain with logging
supervisor_chain = (
    {"input": RunnablePassthrough()}
    | supervisor_prompt
    | model.bind(callbacks=[lambda x: print(f"Supervisor LLM Output: {x.content}")])
    | StrOutputParser().bind(callbacks=[log_intermediate])
)

# Create the LangGraph graph
workflow = Graph()
workflow.add_node("supervisor", supervisor_chain)
workflow.set_entry_point("supervisor")

# Compile the graph
top_supervisor = workflow.compile(name="SCADAgric")



@cl.on_chat_start
async def main():
    cl.user_session.set("agent", top_supervisor)
    await cl.Message(content="Hello! How can I help you with your smart farm today?").send()

@cl.on_message
async def run(message: cl.Message):
    agent = cl.user_session.get("agent")  # type: Runnable
    res = await agent.ainvoke(message.content)
    print(f"Supervisor Result: {res}")

    if "visualize_sensor_data" in res.get("intermediate_steps", []):
        try:
            plotly_json = res["last_step_output"]
            cl_plot = cl.Plotly(content=plotly_json)
            await cl_plot.send()
        except Exception as e:
            await cl.Message(content=f"Error displaying visualization: {e}").send()
    elif isinstance(res["last_step_output"], str):
        await cl.Message(content=res["last_step_output"]).send()
    elif isinstance(res["last_step_output"], dict):
        await cl.Message(content=json.dumps(res["last_step_output"], indent=2)).send()
    else:
        await cl.Message(content="Operation completed.").send()

# # Create the supervisor workflow
# top_supervisor = create_supervisor(
#     agents=[sensor_visualization_agent, sensor_extraction_agent],
#     model=model,
#     prompt=(
#         "You are a Farm Supervisor Agent responsible for managing specialized agents that handle smart farm queries. "
#         "Delegate tasks according to the query's focus:\n\n"
#         "- Use `sensor_extraction_agent` for identifying sensor IDs and fetching telemetry data from ThingsBoard.\n"
#         "- Use `sensor_visualization_agent` for generating time series charts and visualizations of sensor data.\n"
#         "- Use `weather_agent` for handling weather-related queries like forecasts or historical weather data.\n"
#         "- Use `alert_agent` for processing and delivering alerts based on sensor thresholds or system status.\n\n"
#         "Analyze the user request and route it to the most appropriate agent. Only one agent should be assigned per task."
#     )
# ).compile(name="SCADAgric")

# # --- Example Usage ---
# input_query = "Get me temperature  plot  in north and central field."
# inputs = {"messages": [HumanMessage(content=input_query)]}
# result = sensor_visualization_agent.invoke(inputs)

# # Print result
# for msg in result["messages"]:
#     msg.pretty_print()