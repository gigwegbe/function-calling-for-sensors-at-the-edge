import os
import json
import requests
from time import time
from datetime import datetime
from typing import List, Optional
import pytz

import chainlit as cl
from langchain_openai import ChatOpenAI

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from pydantic import BaseModel, Field
from dotenv import load_dotenv

from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_core.messages import SystemMessage
from langchain_core.runnables import Runnable
from langchain.chains.openai_functions import create_openai_fn_runnable
from langgraph.prebuilt import create_react_agent
from langgraph_supervisor import create_supervisor

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
            # Use async send to avoid synchronization issues
            cl.run_sync(cl.Message(content=f"Fetching telemetry for device {name} with ID {device_id}").send)
            
            data = fetch_telemetry(
                device_id,
                token,
                keys=input.keys,
                start_ts=start_ts,
                end_ts=end_ts,
                interval=300000
            )

            # Process raw data and convert timestamps to readable format
            processed_data = {}
            for key, values in data.items():
                processed_data[key] = []
                for reading in values:
                    timestamp = reading['ts']
                    value = reading['value']

                    # Convert the timestamp to a readable format
                    readable_time = convert_timestamp_to_readable(timestamp)

                    processed_data[key].append({
                        "timestamp": readable_time,
                        "value": value
                    })
            
            all_data[name] = processed_data

        except Exception as e:
            all_data[name] = {"error": str(e)}
            cl.run_sync(cl.Message(content=f"Error fetching telemetry for {name}: {str(e)}").send)
    
    return all_data

@tool
def visualize_sensor_data(data: dict) -> str:
    """
    Visualizes telemetry data from multiple sensors over time.
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
                trace = go.Scattergl(x=x, y=y, mode='lines+markers', name=f"{sensor_id} - {metric_name}")
                fig.add_trace(trace, row=row, col=1)
                fig.update_yaxes(title_text=f"{sensor_id} - {metric_name}", row=row, col=1)
                break # Assuming only one metric per sensor for now
        row += 1

    fig.update_layout(
        title="Sensor Readings Over Time",
        xaxis_title="Timestamp",
        template="plotly_dark"
    )
    
    # Instead of showing the figure directly, send it to Chainlit
    elements = [
        cl.Plotly(name="sensor_plot", figure=fig)
    ]
    # Use run_sync to handle this in a tool context
    cl.run_sync(cl.Message(content="Here's your sensor data visualization:", elements=elements).send)
    
    return "Visualization created successfully and displayed in the chat."

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
    tools=[sensor_tool, fetch_sensor_telemetry, visualize_sensor_data],
    prompt="You are an expert in visualizing sensor data from a smart farm. You can create time series charts and other visualizations based on the data.",
    name="sensor_visualization_agent"
)

# Modify the supervisor prompt to handle more specific queries
top_supervisor = create_supervisor(
    agents=[sensor_visualization_agent, sensor_extraction_agent],
    model=model,
    prompt=(
        "You are a Farm Supervisor Agent responsible for managing specialized agents that handle smart farm queries.\n\n"
        "IMPORTANT: When a user asks for specific sensor data like temperature, humidity, moisture, etc. from a specific field, "
        "IMMEDIATELY route the query to the sensor_extraction_agent without asking for additional details.\n\n"
        "For example:\n"
        "- If user asks 'get me temperature of the south field' → route to sensor_extraction_agent\n"
        "- If user asks 'show me humidity data from greenhouse sensors' → route to sensor_visualization_agent\n\n"
        "Only ask for more details if the user's query is truly ambiguous and doesn't mention any specific field or measurement."
    )
).compile(name="SCADAgric")


# # --- Chainlit Integration ---
# @cl.on_chat_start
# async def on_chat_start():
#     cl.user_session.set("top_supervisor", top_supervisor)
#     welcome_message = """
#     # 🌱 Welcome to SCADAgric Smart Farm Assistant
    
#     I can help you monitor your farm sensors and visualize data. Try asking me things like:
    
#     - "Show me the temperature readings from field 1"
#     - "What's the soil moisture level in all corn fields?"
#     - "Get humidity data from greenhouse sensors"
#     """
#     await cl.Message(content=welcome_message).send()

# # @cl.on_message
# # async def on_message(message: cl.Message):
# #     supervisor = cl.user_session.get("top_supervisor")
    
# #     try:
# #         # Execute the supervisor workflow with the user query
# #         raw_result = await cl.make_async(supervisor.invoke)({"input": message.content})
        
# #         # Extract the final answer from the result structure
# #         final_answer = None
        
# #         # Based on the error output, the supervisor returns a dictionary with a 'messages' key
# #         # containing a list of AIMessage objects
# #         if "messages" in raw_result and raw_result["messages"]:
# #             # Extract the content from the first message
# #             final_answer = raw_result["messages"][0].content
        
# #         # If we still can't find a proper answer, use a fallback
# #         if not final_answer:
# #             final_answer = "I couldn't process your request properly. Please try rephrasing your question."
        
# #         # Send the final answer
# #         await cl.Message(content=final_answer).send()
        
# #     except Exception as e:
# #         # Handle errors
# #         await cl.Message(content=f"An error occurred: {str(e)}").send()
# #         await cl.Message(content="Please try a different query or check if the ThingsBoard server is running.").send()

# # @cl.on_message
# # async def on_message(message: cl.Message):
# #     supervisor = cl.user_session.get("top_supervisor")
    
# #     try:
# #         # Execute the supervisor workflow with the user query
# #         raw_result = await cl.make_async(supervisor.invoke)({"input": message.content})
        
# #         # Extract the response from the supervisor
# #         if "messages" in raw_result and raw_result["messages"]:
# #             # The supervisor is responding directly - forward this to the user
# #             supervisor_message = raw_result["messages"][0].content
# #             await cl.Message(content=supervisor_message).send()
            
# #             # If the supervisor is asking for more details, we need to wait for user input
# #             # The next user message will trigger this function again
# #             return
            
# #         # If we reach here, the supervisor has delegated to an agent and we should have output
# #         final_answer = None
        
# #         # Try different approaches to extract the final answer
# #         if "output" in raw_result:
# #             final_answer = raw_result["output"]
# #         elif "agent_outcome" in raw_result and "output" in raw_result["agent_outcome"]:
# #             final_answer = raw_result["agent_outcome"]["output"]
# #         elif "steps" in raw_result and raw_result["steps"]:
# #             last_step = raw_result["steps"][-1]
# #             if "output" in last_step:
# #                 final_answer = last_step["output"]
        
# #         # If we still can't find a proper answer, use the raw result as string
# #         if not final_answer:
# #             final_answer = "I couldn't process your request properly. Please try being more specific about which fields or sensors you're interested in."
        
# #         # Send the final answer
# #         await cl.Message(content=final_answer).send()
        
# #     except Exception as e:
# #         # Log the full exception for debugging
# #         import traceback
# #         print(f"Error details: {traceback.format_exc()}")
        
# #         # Handle errors
# #         await cl.Message(content=f"An error occurred: {str(e)}").send()
# #         await cl.Message(content="Please try a different query or check if the ThingsBoard server is running.").send()


# @cl.on_message
# async def on_message(message: cl.Message):
#     supervisor = cl.user_session.get("top_supervisor")
    
#     try:
#         # Add a thinking message for better UX
#         thinking = cl.Message(content="Processing your request...")
#         await thinking.send()
        
#         # Execute the supervisor workflow with the user query
#         raw_result = await cl.make_async(supervisor.invoke)({"input": message.content})
        
#         # Remove the thinking message
#         await thinking.remove()
        
#         # Debug print for analyzing the response structure
#         print(f"Raw supervisor response: {raw_result}")
        
#         # Handle different response patterns from the supervisor
#         if "messages" in raw_result and raw_result["messages"]:
#             # If supervisor is responding directly (asking for clarification)
#             supervisor_message = raw_result["messages"][0].content
            
#             # Check if this is a clarification request or a finished response
#             if "Please provide" in supervisor_message and "details" in supervisor_message:
#                 # This is a clarification request - modify it to be more helpful
#                 more_helpful = (
#                     "I need more specific information to help you. Please clarify which sensors or "
#                     "fields you're interested in. For example:\n"
#                     "- 'Show temperature readings from south field sensor 1'\n"
#                     "- 'What's the soil moisture in corn field 3?'\n"
#                     "- 'Display humidity data from all greenhouse sensors'"
#                 )
#                 await cl.Message(content=more_helpful).send()
#             else:
#                 # Just a regular response from the supervisor
#                 await cl.Message(content=supervisor_message).send()
                
#         # If agent output was returned directly
#         elif "agent_outcome" in raw_result:
#             agent_output = raw_result["agent_outcome"].get("output", "No specific output provided by agent.")
#             await cl.Message(content=agent_output).send()
            
#         # Other potential response structures
#         elif "output" in raw_result:
#             await cl.Message(content=raw_result["output"]).send()
#         else:
#             # Fallback for unknown response structure
#             await cl.Message(content="I processed your request but couldn't format the response properly. Please try a more specific query.").send()
            
#     except Exception as e:
#         # Log the full exception for debugging
#         import traceback
#         print(f"Error details: {traceback.format_exc()}")
        
#         # Handle errors
#         await cl.Message(content=f"An error occurred: {str(e)}").send()
#         await cl.Message(content="Please try a different query or check if the ThingsBoard server is running.").send()


@cl.on_chat_start
async def on_chat_start():
    # Create the supervisor workflow with clear routing instructions
    top_supervisor = create_supervisor(
        agents=[sensor_visualization_agent, sensor_extraction_agent],
        model=model,
        prompt=(
            "You are a Farm Supervisor Agent responsible for managing specialized agents that handle smart farm queries.\n\n"
            "IMPORTANT INSTRUCTION: NEVER respond directly to user queries. Your job is ONLY to route queries to the appropriate agent.\n\n"
            "- Route to `sensor_extraction_agent` for identifying sensors and getting raw telemetry data\n"
            "- Route to `sensor_visualization_agent` for creating charts and visualizations\n\n"
            "Example routing:\n"
            "- 'get temperature data of south field' → sensor_extraction_agent\n"
            "- 'display humidity data for all fields' → sensor_visualization_agent\n"
            "ALWAYS route to one of these agents without asking for clarification."
        )
    ).compile(name="SCADAgric")
    
    cl.user_session.set("top_supervisor", top_supervisor)
    welcome_message = """
    # 🌱 Welcome to SCADAgric Smart Farm Assistant
    
    I can help you monitor your farm sensors and visualize data. Try asking me things like:
    
    - "Show me the temperature readings from field 1"
    - "What's the soil moisture level in all corn fields?"
    - "Get humidity data from greenhouse sensors"
    """
    await cl.Message(content=welcome_message).send()

@cl.on_message
async def on_message(message: cl.Message):
    supervisor = cl.user_session.get("top_supervisor")
    
    try:
        # Show thinking message
        thinking = await cl.Message(content="Processing your request...").send()
        
        # Direct routing for common queries (bypass the supervisor completely)
        query = message.content.lower()
        
        # Try the supervisor first
        try:
            raw_result = await cl.make_async(supervisor.invoke)({"input": message.content})
            
            # Debug logging
            print(f"Full supervisor result: {raw_result}")
            
            # Extract messages from the supervisor response
            if "messages" in raw_result and raw_result["messages"]:
                # Look for the agent's response (either sensor_extraction_agent or sensor_visualization_agent)
                agent_messages = [msg for msg in raw_result["messages"] 
                                if hasattr(msg, 'name') and 
                                (msg.name == 'sensor_extraction_agent' or msg.name == 'sensor_visualization_agent')]
                
                if agent_messages:
                    # Get the latest agent message
                    latest_agent_message = agent_messages[-1].content
                    # Send a new message instead of updating the thinking message
                    await cl.Message(content=latest_agent_message).send()
                    # Remove the thinking message
                    await thinking.remove()
                    return
                
                # If no agent messages, use the supervisor message
                latest_message = raw_result["messages"][-1].content
                # Check if it's a transfer message or a clarification request
                if "transfer" in latest_message.lower() or "hold on" in latest_message.lower():
                    # Skip transfer messages and fall through to direct handling
                    pass
                else:
                    # Send a new message instead of updating the thinking message
                    await cl.Message(content=latest_message).send()
                    # Remove the thinking message
                    await thinking.remove()
                    return
        except Exception as supervisor_error:
            print(f"Supervisor error: {supervisor_error}")
            # Continue to direct handling
        
        # Direct agent handling (fallback if supervisor fails or returns a greeting)
        # Use sensor extraction agent for most queries
        try:
            if "temperature" in query or "temp" in query:
                result = await cl.make_async(sensor_tool.invoke)(query)
                print(f"Sensor extraction result: {result}")
                
                # Get the sensor IDs from the result
                if isinstance(result, dict) and "sensor_id" in result:
                    # Format for telemetry fetching
                    telemetry_input = TelemetryRequest(device_names=result["sensor_id"], keys="temp,relative_humidity")
                    telemetry_result = fetch_sensor_telemetry(telemetry_input)
                    
                    # Remove thinking message
                    await thinking.remove()
                    
                    # Check if we got data
                    if telemetry_result:
                        # Send a new message with the data
                        await cl.Message(content=f"Here's the temperature data for your query:\n\n```json\n{json.dumps(telemetry_result, indent=2)}\n```").send()
                        
                        # Try to visualize
                        try:
                            viz_result = visualize_sensor_data(telemetry_result)
                            print(f"Visualization result: {viz_result}")
                        except Exception as viz_error:
                            print(f"Visualization error: {viz_error}")
                    else:
                        await cl.Message(content="I couldn't find temperature data for that query. Please check if the sensors are online.").send()
                else:
                    # Remove thinking message
                    await thinking.remove()
                    await cl.Message(content="I couldn't identify which sensors to query. Please specify the field more clearly.").send()
                return
                
            elif "humidity" in query:
                # Similar flow for humidity data
                result = await cl.make_async(sensor_tool.invoke)(query)
                print(f"Sensor extraction result: {result}")
                
                if isinstance(result, dict) and "sensor_id" in result:
                    telemetry_input = TelemetryRequest(device_names=result["sensor_id"], keys="relative_humidity")
                    telemetry_result = fetch_sensor_telemetry(telemetry_input)
                    
                    # Remove thinking message
                    await thinking.remove()
                    
                    if telemetry_result:
                        await cl.Message(content=f"Here's the humidity data for your query:\n\n```json\n{json.dumps(telemetry_result, indent=2)}\n```").send()
                        
                        # Try to visualize
                        try:
                            viz_result = visualize_sensor_data(telemetry_result)
                            print(f"Visualization result: {viz_result}")
                        except Exception as viz_error:
                            print(f"Visualization error: {viz_error}")
                    else:
                        await cl.Message(content="I couldn't find humidity data for that query. Please check if the sensors are online.").send()
                else:
                    # Remove thinking message
                    await thinking.remove()
                    await cl.Message(content="I couldn't identify which sensors to query. Please specify the field more clearly.").send()
                return
            
            else:
                # Generic query - try sensor extraction by default
                result = await cl.make_async(sensor_tool.invoke)(query)
                print(f"Sensor extraction result: {result}")
                
                if isinstance(result, dict) and "sensor_id" in result:
                    telemetry_input = TelemetryRequest(device_names=result["sensor_id"], keys="temp,moisture_content,relative_humidity,soil_conductivity")
                    telemetry_result = fetch_sensor_telemetry(telemetry_input)
                    
                    # Remove thinking message
                    await thinking.remove()
                    
                    if telemetry_result:
                        await cl.Message(content=f"Here's the sensor data for your query:\n\n```json\n{json.dumps(telemetry_result, indent=2)}\n```").send()
                        
                        # Try to visualize
                        try:
                            viz_result = visualize_sensor_data(telemetry_result)
                            print(f"Visualization result: {viz_result}")
                        except Exception as viz_error:
                            print(f"Visualization error: {viz_error}")
                    else:
                        await cl.Message(content="I couldn't find sensor data for that query. Please check if the sensors are online.").send()
                else:
                    # Remove thinking message
                    await thinking.remove()
                    await cl.Message(content="I couldn't identify which sensors to query. Please specify what you're looking for more clearly.").send()
                return
                
        except Exception as direct_error:
            print(f"Direct handling error: {direct_error}")
            # Remove thinking message
            await thinking.remove()
            await cl.Message(content=f"I had trouble processing your request. Please try again with more details about which field or sensor you're interested in.").send()
            return
        
        # Final fallback
        # Remove thinking message
        await thinking.remove()
        await cl.Message(content="I processed your request but couldn't get the right data. Could you try being more specific about which sensors or fields you're interested in?").send()
        
    except Exception as e:
        # Log the full exception for debugging
        import traceback
        print(f"Error details: {traceback.format_exc()}")
        
        try:
            # Try to remove the thinking message if it exists
            await thinking.remove()
        except:
            pass
            
        # Handle errors
        await cl.Message(content=f"An error occurred: {str(e)}").send()
        await cl.Message(content="Please try a different query or check if the ThingsBoard server is running.").send()
if __name__ == "__main__":
    # This part will be handled by the Chainlit CLI
    pass