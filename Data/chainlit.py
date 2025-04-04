from openai import AsyncOpenAI
import chainlit as cl
import requests
import json

client = AsyncOpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")

# Instrument the OpenAI client
cl.instrument_openai()

# API Endpoints
REALTIME_TELEMETRY_URL = "http://127.0.0.1:5000/realtime-telemetry"
DATABASE_TELEMETRY_URL = "http://127.0.0.1:5000/database-telemetry"
ALERTS_URL = "http://127.0.0.1:5000/check-alerts"

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

    if "alerts" in user_message:
        data = fetch_telemetry_data(ALERTS_URL)
        alerts = data.get("alerts", [])
        if alerts:
            alert_messages = "\n".join(alerts)
            response_content = f"Alerts:\n{alert_messages}"
        else:
            response_content = "No alerts at the moment."
    elif "realtime" in user_message:
        data = fetch_telemetry_data(REALTIME_TELEMETRY_URL)
        response_content = f"Real-time Telemetry Data:\n{json.dumps(data, indent=2)}"
    elif "database" in user_message:
        data = fetch_telemetry_data(DATABASE_TELEMETRY_URL)
        response_content = f"Database Telemetry Data:\n{json.dumps(data, indent=2)}"
    else:
        response_content = "Specify 'alerts', 'realtime', or 'database' for telemetry data."

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
                "content": response_content,
                "role": "user"
            }
        ],
        **settings
    )

    await cl.Message(content=response.choices[0].message.content).send()
