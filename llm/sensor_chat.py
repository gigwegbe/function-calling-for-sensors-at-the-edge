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

# Function to fetch telemetry data
def fetch_telemetry_data(endpoint):
    try:
        response = requests.get(endpoint)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}

# Function to summarize telemetry data
def summarize_data(data):
    summary = {}
    for key, values in data.items():
        if isinstance(values, list) and values:
            # Extract numerical values from dictionaries and convert to float
            numerical_values = [float(v['value']) for v in values if isinstance(v, dict) and 'value' in v]
            if numerical_values:
                summary[key] = {
                    "min": min(numerical_values),
                    "max": max(numerical_values),
                    "avg": sum(numerical_values) / len(numerical_values)
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
                                 "✅ `realtime device123`\n"
                                 "✅ `database f7d89db0-fb62-11ef-bd48-432ae725fd12`").send()
        return

    # Extract telemetry type & device ID
    match = re.search(r"(realtime|database)?\s*([\w-]+)", user_input)

    if not match:
        await cl.Message(content="❌ Please provide a valid telemetry request.\n\n"
                                 "**Example usage:**\n"
                                 "✅ `realtime device123`\n"
                                 "✅ `database f7d89db0-fb62-11ef-bd48-432ae725fd12`").send()
        return

    command, device_id = match.groups()
    command = command if command else "realtime"  # Default to realtime

    # Fetch telemetry data from API
    endpoint = f"{BASE_API_URL}/{command}-telemetry/{device_id}"
    data = fetch_telemetry_data(endpoint)

    if "error" in data:
        await cl.Message(content=f"⚠️ Error retrieving telemetry: {data['error']}").send()
        return

    # Summarize the telemetry data
    summarized_data = summarize_data(data)

    # 🔹 **Force user-friendly output**
    prompt = f"""
    You are a telemetry assistant. Present the summarized telemetry data for {device_id} in a **clear and structured** format.
    
    ### 📡 **Telemetry Data for {device_id}**
    - 🌡 **Temperature:** [List min, max, and average values in Fahrenheit]
    - 💧 **Humidity:** [List min, max, and average humidity % if available]
    - 📏 **Pressure:** [List min, max, and average pressure in inHg if available]
    - 🔋 **Battery Level:** [List min, max, and average % if available]

    **⚠️ Important:** The response **must** follow the format above without extra explanations or metadata.

    🔹 **Summarized data:** {summarized_data}
    """

    # 🔥 Invoke LLM
    result = llm.invoke(prompt)

    # ✅ Extract the content from the AIMessage object
    clean_response = result.content.strip()

    # 🚀 Send the cleaned response
    await cl.Message(content=clean_response).send()