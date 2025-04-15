import requests
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
import chainlit as cl

# Load environment variables
load_dotenv()
# python path = # /Users/george/Downloads/eai_methods/env

# API Endpoints
REALTIME_TELEMETRY_URL = "http://127.0.0.1:5000/realtime-telemetry"
DATABASE_TELEMETRY_URL = "http://127.0.0.1:5000/database-telemetry"

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
    user_message = message.content.lower()
    llm = cl.user_session.get("llm")
    
    if "realtime" in user_message:
        data = fetch_telemetry_data(REALTIME_TELEMETRY_URL)
    elif "database" in user_message:
        data = fetch_telemetry_data(DATABASE_TELEMETRY_URL)
    else:
        data = {"message": "Specify 'realtime' or 'database' for telemetry data."}
    
    # Convert dictionary to formatted string
    formatted_data = f"Telemetry Data: {data}"  

    # Invoke LLM with formatted input
    result = llm.invoke(formatted_data)
    
    await cl.Message(content=result).send()

