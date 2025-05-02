from openai import AsyncOpenAI
import chainlit as cl
import requests
import json  # Import JSON for serialization

client = AsyncOpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")

# Instrument the OpenAI client
cl.instrument_openai()

# API Endpoints
REALTIME_TELEMETRY_URL = "http://127.0.0.1:5000/realtime-telemetry"
DATABASE_TELEMETRY_URL = "http://127.0.0.1:5000/database-telemetry"

settings = {
    "model": "lmstudio-community/Llama-3-Groq-8B-Tool-Use-GGUF",
    "temperature": 0,
    # ... more settings
}

# Function to fetch telemetry data
def fetch_telemetry_data(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}

@cl.on_message
async def on_message(message: cl.Message):
    user_message = message.content.lower()
    
    if "realtime" in user_message:
        data = fetch_telemetry_data(REALTIME_TELEMETRY_URL)
    elif "database" in user_message:
        data = fetch_telemetry_data(DATABASE_TELEMETRY_URL)
    else:
        data = {"message": "Specify 'realtime' or 'database' for telemetry data."}

    # Convert telemetry data to a formatted JSON string
    data_str = json.dumps(data, indent=2)

    response = await client.chat.completions.create(
        messages=[
            {
                "content": "You are a helpful assistant.",
                "role": "system", 
            },
            {
                "content": message.content,
                "role": "user"
            },
            {
                "content": data_str, 
                "role": "user"
            }
        ],
        **settings
    )

    await cl.Message(content=response.choices[0].message.content).send()
