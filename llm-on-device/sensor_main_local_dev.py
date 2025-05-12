# from langchain_core.tools import tool
# from langchain_openai import ChatOpenAI
# from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
# from langchain_core.messages import SystemMessage, HumanMessage
# from langchain_core.runnables import Runnable
# from langchain.chains.openai_functions import create_openai_fn_runnable
# from pydantic import BaseModel, Field
# from typing import List, Optional
# import json
# import os
# import requests
# from dotenv import load_dotenv
# from langgraph.prebuilt import create_react_agent
# from datetime import datetime, timedelta
# from time import time
# import pytz

# import plotly.graph_objects as go
# from langchain_core.tools import tool
# from plotly.subplots import make_subplots
# from langgraph_supervisor import create_supervisor
# import chainlit as cl
# from langchain.schema.runnable.config import RunnableConfig
# from langchain_core.messages import AIMessage, HumanMessage
# import chainlit as cl
# import uuid 
# import subprocess
# from chainlit.server import app as fastapi_app
# from fastapi import Request
# import re
# from langgraph.checkpoint.memory import MemorySaver
# from langsmith import utils
# from langchain_community.chat_models import ChatOllama
# # from langgraph.prebuilt.tool_calling import create_structured_chat_agent

# # --- Configuration ---
# THINGSBOARD_URL = "http://localhost:8080"
# USERNAME = "tenant@thingsboard.org"
# PASSWORD = "tenant"

# THINGSBOARD_HOST = "http://localhost:8080"
# USERNAME = "tenant@thingsboard.org"
# PASSWORD = "tenant"

# # Shared message queue
# incoming_messages = []

# # --- Load API Keys and Initialize Model ---
# load_dotenv()
# # openai_api_key = os.getenv("OPENAI_PROJECT_API_KEY")
# # model = ChatOpenAI(api_key=openai_api_key, model="gpt-4o", temperature=0)
# model = ChatOllama(
#     model="llama3.2",
#     keep_alive=-1, # keep the model loaded indefinitely
#     temperature=0,
#     max_new_tokens=2000)

# utils.tracing_is_enabled()

# # --- Load Farm Data ---
# def load_farm_data():
#     with open("farm_model_smaller.json") as f:
#         farm_data = json.load(f)
#     return json.dumps(farm_data["farm"]["fields"], indent=2)

# farm_description = load_farm_data()


# def load_farm_control_data():
#     with open("farm_model_control.json") as f:
#         farm_data = json.load(f)
#     return json.dumps(farm_data["farm"]["fields"], indent=2)

# farm_control_description = load_farm_control_data()


# # --- ThingsBoard API Interactions ---
# def get_jwt_token():
#     url = f"{THINGSBOARD_URL}/api/auth/login"
#     response = requests.post(url, json={"username": USERNAME, "password": PASSWORD})
#     response.raise_for_status()
#     return response.json()["token"]

# def get_device_id_by_name(device_name, token):
#     url = f"{THINGSBOARD_URL}/api/tenant/devices?deviceName={device_name}"
#     headers = {"X-Authorization": f"Bearer {token}"}
#     response = requests.get(url, headers=headers)
#     response.raise_for_status()
#     return response.json().get("id", {}).get("id")

# def fetch_telemetry(device_id, token, keys="temp,moisture_content,relative_humidity,soil_conductivity", start_ts=None, end_ts=None, interval=18000):
#     url = f"{THINGSBOARD_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
#     headers = {"X-Authorization": f"Bearer {token}"}
#     params = {
#         "keys": keys,
#         "startTs": start_ts,
#         "endTs": end_ts,
#         "interval": interval,
#         "limit": 50,
#         "agg": "NONE"
#     }
#     response = requests.get(url, headers=headers, params=params)
#     response.raise_for_status()
#     return response.json()

# # --- Sensor Extraction Tooling ---
# class SensorExtraction(BaseModel):
#     sensor_id: List[str] = Field(..., description="List of sensor IDs relevant to the query")

# def build_prompt_sensor(farm_description: str):
#     system_message = SystemMessage(
#         content=(
#             "You are a smart farm assistant. Based on the user query and this farm data, extract sensor IDs.\n"
#             "Respond ONLY with a JSON object in this format: {\"sensor_id\": [...]}\n\n"
#             f"Farm field data:\n{farm_description}"
#         )
#     )
#     human_message = HumanMessagePromptTemplate.from_template("{input}")
#     return ChatPromptTemplate.from_messages([system_message, human_message])

# def build_sensor_extraction_tool(model, prompt_template) -> Runnable:
#     runnable = create_openai_fn_runnable([SensorExtraction], model, prompt_template)

#     @tool
#     def sensor_extraction(input: str) -> dict:
#         """Extract relevant sensor IDs from a user query about farm fields."""
#         return runnable.invoke({"input": input})

#     return sensor_extraction

# # --- Telemetry Fetching Tooling ---
# class TelemetryRequest(BaseModel):
#     device_names: List[str] = Field(..., description="List of device names to query telemetry for")
#     keys: str = Field("temp,moisture_content,relative_humidity,soil_conductivity", description="Comma-separated telemetry keys to fetch (e.g., temp,humidity)")
#     # hours: Optional[int] = Field(24, description="How many hours back to fetch data from")


# def convert_timestamp_to_readable(ts, timezone="UTC"):
#     # Convert milliseconds to seconds
#     timestamp_in_seconds = ts / 1000
#     # Convert to UTC datetime
#     utc_time = datetime.utcfromtimestamp(timestamp_in_seconds)
    
#     # Set the timezone to UTC
#     utc_time = pytz.utc.localize(utc_time)
    
#     kigali_tz = pytz.timezone('Africa/Kigali')
#     # Convert to the desired timezone (e.g., Europe/Paris)
#     local_time = utc_time.astimezone(kigali_tz)
    
#     # Format the datetime to a readable string
#     readable_time = local_time.strftime('%Y-%m-%d %H:%M:%S')
#     return readable_time

# @tool
# def fetch_sensor_telemetry(input: TelemetryRequest) -> dict:
#     """
#     Fetch telemetry data for a list of device names and keys from ThingsBoard over the past N hours.
#     """
#     token = get_jwt_token()
#     end_ts = int(time() * 1000)  # Current time in milliseconds
#     start_ts = end_ts - 24 * 60 * 60 * 1000  # Last 24 hours

#     all_data = {}

#     for name in input.device_names:
#         try:
#             device_id = get_device_id_by_name(name, token)
#             print(f"=============={device_id}===================")
#             print(f"Fetching telemetry for device {name} with ID {device_id}")
#             data = fetch_telemetry(
#                 device_id,
#                 token,
#                 keys=input.keys,
#                 start_ts=start_ts,
#                 end_ts=end_ts,
#                 interval=18000
#             )
#             print(f"Raw data for {name}: {data}")  # Log raw data to debug

#             # Process raw data and convert timestamps to readable format
#             processed_data = {}
#             for key, values in data.items():
#                 processed_data[key] = []
#                 for reading in values:
#                     timestamp = reading['ts']  # Access 'ts' field from reading
#                     value = reading['value']   # Access 'value' field

#                     # Convert the timestamp to a readable format
#                     readable_time = convert_timestamp_to_readable(timestamp)

#                     processed_data[key].append({
#                         "timestamp": readable_time,
#                         "value": value
#                     })
            
#             all_data[name] = processed_data

#         except Exception as e:
#             all_data[name] = {"error": str(e)}
#             print(f"Error fetching telemetry for {name}: {e}")
    
#     return all_data


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


# def get_device_access_token(token, device_id):
#     if not device_id:
#         return None
    
#     url = f"{THINGSBOARD_URL}/api/device/{device_id}/credentials"
#     headers = {'Content-Type': 'application/json', 'X-Authorization': f'Bearer {token}'}
#     try:
#         response = requests.get(url, headers=headers)
#         response.raise_for_status()
#         credentials_data = response.json()
#         return credentials_data.get('credentialsId')
#     except requests.exceptions.RequestException as e:
#         print(f"Error retrieving device credentials: {e}")
#         return None


# # # Step 1: Authenticate
# def login():
#     url = f"{THINGSBOARD_URL}/api/auth/login"
#     response = requests.post(url, json={"username": USERNAME, "password": PASSWORD})
#     response.raise_for_status()
#     return response.json()["token"]

# # Step 2: Get all rule chains
# def get_all_rule_chains(token):
#     url = f"{THINGSBOARD_URL}/api/ruleChains?pageSize=100&page=0"
#     headers = {"X-Authorization": f"Bearer {token}"}
#     response = requests.get(url, headers=headers)
#     response.raise_for_status()
#     return response.json()["data"]

# # Step 3: Delete each rule chain
# def delete_rule_chain(base_url, token, rule_chain_id):
#     url = f"{base_url}/api/ruleChain/{rule_chain_id}"
#     headers = {"X-Authorization": f"Bearer {token}"}
#     response = requests.delete(url, headers=headers)
#     if response.status_code == 200:
#         print(f"Deleted rule chain: {rule_chain_id}")
#     else:
#         print(f"Failed to delete {rule_chain_id}: {response.text}")

# @tool
# # Main function
# def delete_all_alerts_rule_chain():
#     """
#     Deletes all non-root rule chains in ThingsBoard.

#     This function logs into the ThingsBoard server using the configured login function,
#     retrieves all rule chains, and deletes each one except the root rule chain.
    
#     Make sure THINGSBOARD_URL and login/get_all_rule_chains/delete_rule_chain
#     are defined and working in your script.
#     """
#     token = login()
#     rule_chains = get_all_rule_chains(token)
#     for rc in rule_chains:
#         if not rc.get("root"):  # optionally skip root chain
#             delete_rule_chain(THINGSBOARD_URL, token, rc["id"]["id"])


# @tool
# def visualize_sensor_data(data: dict) -> str:
#     """
#     Visualizes telemetry data from multiple sensors over time and saves the plot as a PNG image.

#     Args:
#         data (dict): A nested dictionary of the form {sensor_id: {metric_name: [{"timestamp": ..., "value": ...}, ...]}}

#     Returns:
#         str: The filename of the saved plot image ("plot.png").
#     """
#     num_sensors = len(data)
#     if num_sensors == 0:
#         return "No sensor data available for visualization."

#     fig = make_subplots(rows=num_sensors, cols=1, shared_xaxes=True, vertical_spacing=0.1)
#     row = 1
#     for sensor_id, sensor_metrics in data.items():
#         for metric_name, readings in sensor_metrics.items():
#             x = [datetime.strptime(reading['timestamp'], '%Y-%m-%d %H:%M:%S') for reading in readings]
#             y = [float(reading['value']) for reading in readings]
#             if x and y:
#                 trace = go.Scattergl(x=x, y=y, mode='lines+markers', name=f"{sensor_id} - {metric_name}")
#                 fig.add_trace(trace, row=row, col=1)
#                 fig.update_yaxes(title_text=f"{sensor_id} - {metric_name}", row=row, col=1)
#                 break
#         row += 1

#     fig.update_layout(
#         title="Sensor Readings Over Time",
#         xaxis_title="Timestamp",
#         template="plotly_dark"
#     )

#     # Save the figure as a PNG file
#     filename = "plot.png"
#     fig.write_image(filename)
#     return filename

# class AlertScriptInput(BaseModel):
#     sensor_name: str = Field(..., description="Name of the sensor to alert on")
#     threshold: float = Field(..., description="Threshold value to trigger alert")


# @tool
# def run_alert_script(input: AlertScriptInput) -> dict:
#     """
#     Executes the external Python script 'alert.py' with the provided sensor name and threshold.

#     Args:
#         input (AlertScriptInput): Contains the sensor name and threshold.

#     Returns:
#         dict: Execution result including stdout or error.
#     """
#     try:
#         result = subprocess.run(
#             ["python", "alert_with_threshold.py", input.sensor_name, str(input.threshold)],
#             capture_output=True,
#             text=True,
#             check=True
#         )
#         return {
#             "stdout": result.stdout,
#             "stderr": result.stderr
#         }
#     except subprocess.CalledProcessError as e:
#         return {
#             "error": e.stderr
#         }

# @tool
# def control_actuator(device_name: str, device_state: int) -> str:
#     """Control an actuator (e.g., turn ON/OFF) by device name and desired state (1=ON, 0=OFF)."""
#     try:
#         jwt_token = get_jwt_token()
#         device_id = get_device_id_by_name(device_name, jwt_token)
#         if not device_id:
#             return f"Device '{device_name}' not found."

#         access_token = get_device_access_token(jwt_token, device_id)
#         if not access_token:
#             return f"Access token for '{device_name}' not found."

#         telemetry_url = f"{THINGSBOARD_HOST}/api/v1/{access_token}/telemetry"
#         payload = {"deviceState": device_state}
#         headers = {"Content-Type": "application/json"}

#         response = requests.post(telemetry_url, headers=headers, data=json.dumps(payload))
#         if response.status_code == 200:
#             return f"Successfully set state of '{device_name}' to {'ON' if device_state == 1 else 'OFF'}."
#         else:
#             return f"Failed to control actuator '{device_name}': {response.status_code} - {response.text}"
#     except Exception as e:
#         return f"Error while controlling actuator '{device_name}': {str(e)}"
    


# # === FUNCTION SCHEMA ===
# class ActutatorExtraction(BaseModel):
#     actuator_id: List[str] = Field(..., description="List of actuators IDs relevant to the query")

# # === TOOL WRAPPING ===
# def build_control_extraction_tool(model, prompt_template) -> Runnable:
#     runnable = create_openai_fn_runnable([ActutatorExtraction], model, prompt_template)

#     @tool
#     def control_extraction(input: str) -> dict:
#         """Extract relevant actuator IDs from a user query about farm fields."""
#         return runnable.invoke({"input": input})

#     return control_extraction



# def build_prompt_control(farm_control_description: str):
#     system_message = SystemMessage(
#         content=(
#             "You are a smart farm assistant designed to extract actuator IDs based on user queries and farm field data.\n\n"
#             "Your task is to identify actuators related to WATER or FERTILIZER control. These include:\n"
#             "- PUMPS: IDs like `PUMP-0300`, `PUMP-0301`  \n"
#             "- VALVES: IDs like `WV-0300` (for water), `FD-0300` (for fertilizer)\n\n"
#             "**Naming Conventions:**\n"
#             "- PUMP-xxxx:\n"
#             "  - Ends with `00` → Water pump (e.g., PUMP-0300)\n"
#             "  - Ends with `00` → Water pump (e.g., PUMP-0300)\n"
#             "  - Ends with `01` → Fertilizer pump (e.g., PUMP-0301)\n"
#             "- WV-xxxx → Water valve\n"
#             "- FD-xxxx → Fertilizer valve\n\n"
#             "**Instructions:**\n"
#             "- Only include actuator IDs that are relevant to the query.\n"
#             "- Do not include sensor IDs or unrelated components.\n"
#             "- Your response must be a JSON object ONLY in the following format:\n"
#             "  {\"actuator_id\": [\"PUMP-0301\", \"FD-0300\", ...]}\n\n"
#             "**Farm Field Data:**\n"
#             f"{farm_control_description}"
#         )
#     )
#     human_message = HumanMessagePromptTemplate.from_template("{input}")
#     return ChatPromptTemplate.from_messages([system_message, human_message])



# # --- Initialize Langchain Agent ---
# prompt_template = build_prompt_sensor(farm_description)
# sensor_tool = build_sensor_extraction_tool(model, prompt_template)
# sensor_extraction_agent = create_react_agent(
#     model=model,
#     tools=[sensor_tool, fetch_sensor_telemetry],
#     prompt="You are an expert in identifying relevant sensor IDs from natural language farm queries.",
#     name="sensor_extraction_agent"
# )



# alert_agent = create_react_agent(
#     model,
#     tools=[sensor_tool, run_alert_script, delete_all_alerts_rule_chain],
#     prompt=(
#         "You are an alert assistant. Your task is to process natural language queries related to sensor alerts. "
#         "First, extract the sensor name using the `sensor_tool` and determine the threshold value from the query. "
#         "Then, trigger the `run_alert_script` tool with these extracted arguments. "
#         "If the user wants to remove existing alerts, use the `delete_all_alerts_rule_chain` tool."
#     ),
#     name="alert_agent"
# )

# sensor_visualization_agent = create_react_agent(
#     model=model,
#     tools=[sensor_tool, fetch_sensor_telemetry, visualize_sensor_data],  # Add the visualization tool
#     prompt="You are an expert in visualizing sensor data from a smart farm. You can create time series charts and other visualizations based on the data. Make the plot fast.",
#     name="sensor_visualization_agent"
# )


# prompt_control_template = build_prompt_control(farm_control_description)
# control_tool = build_control_extraction_tool(model, prompt_control_template)
# control_extraction_agent = create_react_agent(
#     model=model,
#     tools=[control_tool, control_actuator],
#     prompt=(
#         "You are a smart farm assistant specializing in identifying and extracting actuator IDs from natural language queries.\n\n"
#         "Your primary goal is to understand a user's request about field operations and extract the correct **actuator IDs** using the provided tools.\n\n"
#         "### 🔧 Actuator Types:\n"
#         "- **PUMPS** for water or fertilizer (e.g., `PUMP-0300`, `PUMP-0301`)\n"
#         "- **VALVES** for water or fertilizer (e.g., `WV-0300`, `FD-0300`)\n\n"
#         "### 🧭 Naming Conventions:\n"
#         "- `PUMP-xxxx`\n"
#         "   - Ends in `00` → Water pump\n"
#         "   - Ends in `01` → Fertilizer pump\n"
#         "- `WV-xxxx` → Water valves\n"
#         "- `FD-xxxx` → Fertilizer valves\n\n"
#         "### 🧠 Your Task:\n"
#         "1. Read and understand the user query.\n"
#         "2. Determine whether the request is about **water** or **fertilizer**.\n"
#         "3. Identify the correct actuator types (**pump** or **valve**).\n"
#         "4. Use the `control_tool` to extract relevant actuator IDs from available farm data.\n"
#         "5. Use the `control_actuator` tool to apply the desired action (turn ON/OFF).\n\n"
#         "### 📤 Output Format:\n"
#         "Return the result as a JSON object in this format:\n"
#         "`{\"actuator_ids\": [\"ACTUATOR_ID1\", \"ACTUATOR_ID2\", ...]}`\n\n"
#         "⚠️ Do not make up actuator IDs. You must use the provided `control_tool` to extract them.\n"
#         "⚠️ To control an actuator, use the `control_actuator` tool with the actuator name and desired state:\n"
#         "- `1` = ON\n"
#         "- `0` = OFF"
#     ),
#     name="control_extraction_agent"
# )
# #  If returned the operation temperature is more than 28 degree recommend irrigation do not irrigate except when I tell you to do so

# top_supervisor = create_supervisor(
#     agents=[sensor_visualization_agent, sensor_extraction_agent, alert_agent, control_extraction_agent],
#     model=model,
#     prompt=(
#         "You are a Farm Supervisor Agent responsible for managing specialized agents that handle smart farm queries."
#         "Delegate tasks according to the query's focus:\n\n"
#         "When you get user input e.g 'Farm summary' Get the recent last sensor readings for all the sensors( temperature, soil moisture, humidity, soil conductivity) in the north field using the  `sensor_extraction_agent` and only show the readings not visuals or plot"
#         "- Use `sensor_extraction_agent` for identifying sensor IDs and fetching telemetry data from ThingsBoard.\n"
#         "- Use `sensor_visualization_agent` for generating time series charts and visualizations of sensor data. Make the plot fast.\n"
#         "- Use `alert_agent` for processing and delivering alerts based on sensor thresholds or system status.\n\n"
#         "- Use `control_extraction_agent` for controlling actuators e.g pump, valve and fertilizer dispenser based NOTE ON - 1 and OFF - 0 .\n\n"
#         "Analyze the user request and route it to the most appropriate agent. Only one agent should be assigned per task."
#     )
# ).compile(name="SCADAgric")



# @cl.on_chat_start
# async def main():
#     # await cl.Message(content="Hello World").send()
#     pass


# @cl.set_starters
# async def set_starters():
#     return [
#         cl.Starter(
#             label="Farm Summary",
#             message="What is the farm summary in the north field?",
#             icon="/public/idea.svg",
#         ),
#         cl.Starter(
#             label="Realtime Information",
#             message="Give me realtime data.",
#             icon="/public/write.svg",
#         ),
#         cl.Starter(
#             label="How to control a pump?",
#             message="Control the actuactor.",
#             icon="/public/pump.png", 
#         ),
#         cl.Starter(
#             label="Get Farm Alert",
#             message="Create alert.",
#             icon="/public/terminal.svg",
#         ),
#         cl.Starter(
#             label="Get Farm Weather",
#             message="What is the weather in  Nyagatare District, Eastern Province, Rwanda.",
#             icon="/public/cloudy.png",
#         ),
#     ]



# @cl.on_message
# async def on_message(message: cl.Message):
#     config = {"configurable": {"thread_id": cl.context.session.id}}
#     cb = cl.LangchainCallbackHandler()
    
#     # Track final response and whether we found and sent a plot
#     final_response = ""
#     plot_file = "plot.png"
#     plot_sent = False
    
#     # Stream responses from the supervisor
#     async for output in top_supervisor.astream(
#         {"messages": [HumanMessage(content=message.content)]},
#         config=RunnableConfig(callbacks=[cb], **config)
#     ):
#         print(f"Output step: {output}")
        
#         # Check if visualization agent has created a plot
#         if "sensor_visualization_agent" in output:
#             agent_output = output["sensor_visualization_agent"]
#             if agent_output and "messages" in agent_output:
#                 # Look through messages for the plot filename
#                 for msg in agent_output["messages"]:
#                     if isinstance(msg, AIMessage) and plot_file in msg.content:
#                         try:
#                             # Check if file exists before sending
#                             if os.path.exists(plot_file):
#                                 with open(plot_file, "rb") as f:
#                                     content = f.read()
                                
#                                 # Extract explanation text without markdown artifacts
#                                 explanation = msg.content
                                
#                                 # Remove markdown image syntax patterns
#                                 explanation = re.sub(r'!\[.*?\]\(.*?\)', '', explanation)
#                                 explanation = re.sub(r'!\[.*?\]\(', '', explanation)
#                                 explanation = explanation.replace(plot_file, '').strip()
                                
#                                 # Default explanation if empty after cleaning
#                                 if not explanation:
#                                     explanation = "Here is the sensor data visualization:"
                                
#                                 # Send the image with explanation
#                                 await cl.Message(
#                                     content=explanation,
#                                     elements=[
#                                         cl.Image(
#                                             name="Sensor Plot",
#                                             display="inline",
#                                             id=str(uuid.uuid4()),
#                                             content=content,
#                                             size="large"
#                                         )
#                                     ]
#                                 ).send()
#                                 plot_sent = True
#                         except Exception as e:
#                             print(f"Error displaying plot: {str(e)}")
#                             await cl.Message(content=f"Error displaying the plot: {str(e)}").send()
        
#         # Get final response from supervisor
#         if "supervisor" in output:
#             supervisor_output = output["supervisor"]
#             if supervisor_output and "messages" in supervisor_output:
#                 for msg in supervisor_output["messages"]:
#                     if isinstance(msg, AIMessage):
#                         # Clean markdown image artifacts from text responses too
#                         response_text = msg.content
#                         response_text = re.sub(r'!\[.*?\]\(.*?\)', '', response_text)
#                         response_text = re.sub(r'!\[.*?\]\(', '', response_text)
#                         final_response = response_text.strip()
    
#     # If we haven't sent a plot yet, send the text response
#     if not plot_sent and final_response:
#         await cl.Message(content=final_response).send()



# # print(f"==============Tracing=========={utils.tracing_is_enabled()}=======================================")
# # input_query = "Get me temperature  plot  in north and central field."
# # inputs = {"messages": [HumanMessage(content=input_query)]}
# # result = top_supervisor.invoke(inputs)

# # # Print result
# # for msg in result["messages"]:
# #     msg.pretty_print()