import os
import chainlit as cl
from datetime import datetime, timedelta
import plotly.graph_objects as go
from helpers import get_jwt_token, get_device_id_by_name, fetch_telemetry, convert_timestamp_to_readable, extract_time_series, get_metadata_for_sensor

os.makedirs("figures", exist_ok=True)

sensor_ids = []  # Will store extracted sensor IDs from initial input
latest_data = {}  # Will store telemetry for all sensors after fetch

@cl.on_chat_start
def start():
    cl.user_session.set("sensor_ids", [])
    cl.user_session.set("latest_data", {})

@cl.on_message
async def handle_query(message: cl.Message):
    await cl.Message(
        content="Select a time range:",
        actions=[
            cl.Action(name="range", value="6", label="Last 6 Hours"),
            cl.Action(name="range", value="12", label="Last 12 Hours"),
            cl.Action(name="range", value="24", label="Last 24 Hours"),
            cl.Action(name="range", value="168", label="Last 7 Days"),
        ],
    ).send()
    cl.user_session.set("query", message.content)

@cl.action_callback("range")
async def fetch_and_show_buttons(action: cl.Action):
    query = cl.user_session.get("query")
    hours = int(action.value)

    # Extract sensor IDs (you can hook in LLM here if needed)
    extracted = sensor_extraction_agent.invoke({"messages": [cl.Message(content=query)]})
    sensors = extracted["messages"][-1].content
    sensor_ids = eval(sensors).get("sensor_id", [])

    cl.user_session.set("sensor_ids", sensor_ids)

    token = get_jwt_token()
    end_ts = int(datetime.now().timestamp() * 1000)
    start_ts = end_ts - hours * 60 * 60 * 1000

    data = {}
    for sid in sensor_ids:
        try:
            device_id = get_device_id_by_name(sid, token)
            telemetry = fetch_telemetry(device_id, token, start_ts=start_ts, end_ts=end_ts)
            data[sid] = telemetry
        except Exception as e:
            data[sid] = {"error": str(e)}

    cl.user_session.set("latest_data", data)

    await cl.Message(
        content="Choose a sensor to visualize:",
        actions=[cl.Action(name="viz", value=sid, label=f"Visualize {sid}") for sid in sensor_ids]
    ).send()

@cl.action_callback("viz")
async def visualize(action: cl.Action):
    sensor_id = action.value
    data = cl.user_session.get("latest_data").get(sensor_id, {})

    fig = go.Figure()
    for metric, readings in data.items():
        if isinstance(readings, list):
            x, y = extract_time_series(readings)
            if x and y:
                fig.add_trace(go.Scatter(x=x, y=y, mode='lines+markers', name=metric))

    fig.update_layout(title=f"Telemetry for {sensor_id}", xaxis_title="Time", yaxis_title="Value")
    fig_path = f"figures/{sensor_id}.png"
    fig.write_image(fig_path)

    metadata = get_metadata_for_sensor(sensor_id)

    await cl.Message(
        content=f"**Sensor:** {sensor_id}\n**Crop:** {metadata.get('crop', 'Unknown')}\n**Field:** {metadata.get('field_id', 'Unknown')}",
        elements=[cl.Image(name=sensor_id, path=fig_path)]
    ).send()
