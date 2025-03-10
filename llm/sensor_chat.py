import requests
import os
import re
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
import chainlit as cl

# Load environment variables
load_dotenv()

# Base API URL
BASE_API_URL = "http://127.0.0.1:7000"

# Initialize LLM
llm = ChatOpenAI(openai_api_key=os.getenv('OPENAI_PROJECT_API_KEY'), model="gpt-3.5-turbo")

# Store LLM in user session
@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("llm", llm)
    await cl.Message(content="👋 Hello! I'm your telemetry assistant. How can I help you today?").send()

# Function to fetch telemetry data with pagination
def fetch_telemetry_data(endpoint, page=1, page_size=100):
    try:
        print(f"Fetching telemetry data from: {endpoint}")  # Debug print
        response = requests.get(endpoint, params={"page": page, "page_size": page_size})
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching telemetry data: {e}")  # Debug print
        return {"error": str(e)}

# Function to normalize telemetry data structure
def normalize_data(data):
    if isinstance(data, dict):
        # Flatten nested structure
        normalized_data = []
        for key, values in data.items():
            for entry in values:
                normalized_data.append({
                    "ts": entry["ts"],
                    "value": entry["value"]
                })
        return normalized_data
    return data

# Function to summarize telemetry data
def summarize_data(data):
    summary = {}
    for entry in data:
        key = "value"  # Use a single key for all values
        value = entry.get("value")
        if value is not None:
            if key not in summary:
                summary[key] = []
            summary[key].append(float(value))
    
    for key, values in summary.items():
        summary[key] = {
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values)
        }
    
    return summary

@cl.on_message
async def handle_message(message: cl.Message):
    user_input = message.content.strip().lower()
    llm = cl.user_session.get("llm")

    if llm is None:
        await cl.Message(content="⚠️ LLM is not initialized. Please try again later.").send()
        return

    # Check for greeting or help request
    if "hello" in user_input or "hi" in user_input or "help" in user_input:
        await cl.Message(content="👋 Hi there! Please provide a telemetry request.\n\n"
                                 "**Example usage:**\n"
                                 "✅ `realtime f7d89db0-fb62-11ef-bd48-432ae725fd12`\n"
                                 "✅ `database f7d89db0-fb62-11ef-bd48-432ae725fd12`").send()
        return

    # Extract telemetry type & device ID
    match = re.search(r"(realtime|database)?\s*(?:data\s*for\s*id\s*[:\-]?\s*)?([\w-]+)", user_input)

    if not match:
        await cl.Message(content="❌ I couldn't understand your request. Could you please specify whether you need `realtime` or `database` data and provide the device ID?\n\n"
                                 "**Example usage:**\n"
                                 "✅ `realtime f7d89db0-fb62-11ef-bd48-432ae725fd12`\n"
                                 "✅ `database f7d89db0-fb62-11ef-bd48-432ae725fd12`").send()
        return

    command, device_id = match.groups()
    if not command:
        await cl.Message(content="❓ I noticed you didn't specify the type of data. Do you need `realtime` or `database` data?").send()
        return

    if not device_id:
        await cl.Message(content="❓ I noticed you didn't provide a device ID. Could you please provide the device ID?").send()
        return

    # Send a loading message
    await cl.Message(content="⏳ Fetching telemetry data...").send()

    # Fetch telemetry data from API with pagination
    endpoint = f"{BASE_API_URL}/{command}-telemetry/{device_id}"
    data = fetch_telemetry_data(endpoint, page=1, page_size=100)

    if "error" in data:
        await cl.Message(content=f"⚠️ Error retrieving telemetry: {data['error']}").send()
        return

    # Normalize the data structure
    normalized_data = normalize_data(data)

    # Send a processing message
    await cl.Message(content="🔄 Processing telemetry data...").send()

    # Summarize the telemetry data
    summarized_data = summarize_data(normalized_data)

    # 🔹 **Force user-friendly output**
    prompt = f"""
    You are a telemetry assistant, you are allowed to ask for clarification if needed. Stay concise and user-friendly.
    Present the summarized telemetry data for {device_id} in a **clear and structured** format.
    
    ### 📡 **Telemetry Data for {device_id}**
    - 🌡 **Temperature:** [List min, max, and average values in Fahrenheit]
    - 💧 **Humidity:** [List min, max, and average humidity % if available]
    - 📏 **Pressure:** [List min, max, and average pressure in inHg if available]
    - 🔋 **Battery Level:** [List min, max, and average % if available]

    **⚠️ Important:** The response **must** follow the format above without extra explanations or metadata.

    🔹 **Summarized data:** {summarized_data}
    You can use this data to fill in the placeholders in the prompt. 
    """

    # 🔥 Invoke LLM
    result = llm.invoke(prompt)

    # ✅ Extract the content from the AIMessage object
    clean_response = result.content.strip()

    # 🚀 Send the cleaned response
    await cl.Message(content=clean_response).send()