import requests
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
import chainlit as cl

# Load environment variables
load_dotenv()

# Base API URL
BASE_API_URL = "http://127.0.0.1:7000"

# Initialize LLM
llm = ChatOpenAI(openai_api_key=os.getenv('OPENAI_PROJECT_API_KEY'), model="gpt-3.5-turbo")

# Function to fetch telemetry data
def fetch_telemetry_data(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}

@cl.on_chat_start
def setup_chain():
    cl.user_session.set("llm", llm)

@cl.on_message
async def handle_message(message: cl.Message):
    user_message = message.content.lower().split()
    llm = cl.user_session.get("llm")
    
    # Extract device ID from the user's message
    if len(user_message) < 2:
        await cl.Message(content="Please specify a device ID (e.g., 'realtime device123').").send()
        return
    
    command, device_id = user_message[0], user_message[1]

    if command == "realtime":
        data = fetch_telemetry_data(f"{BASE_API_URL}/realtime-telemetry/{device_id}")
    elif command == "database":
        data = fetch_telemetry_data(f"{BASE_API_URL}/database-telemetry/{device_id}")
    else:
        data = {"message": "Specify 'realtime <device_id>' or 'database <device_id>' to get telemetry data."}

    # Convert dictionary to formatted string
    formatted_data = f"Telemetry Data: {data}"

    # Invoke LLM with formatted input
    result = llm.invoke(formatted_data)
    
    await cl.Message(content=result).send()
