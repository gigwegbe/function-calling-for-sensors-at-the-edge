from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import Runnable
from langchain.chains.openai_functions import create_openai_fn_runnable
from pydantic import BaseModel, Field
from typing import List
import json
import os
import requests
from dotenv import load_dotenv
from langgraph.prebuilt import create_react_agent
import requests
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timedelta
from time import time


THINGSBOARD_URL = "http://localhost:8080"
USERNAME = "tenant@thingsboard.org"
PASSWORD = "tenant"
DASHBOARD_ID = "http://localhost:8080/tenants"

DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "thingsboard"
DB_USER = "thingsboard"
DB_PASSWORD = "postgres"


THINGSBOARD_HOST = "http://localhost:8080"
USERNAME = "tenant@thingsboard.org"
PASSWORD = "tenant"


# Load API keys and JSON
load_dotenv()
openai_api_key = os.getenv("OPENAI_PROJECT_API_KEY")
model = ChatOpenAI(api_key=openai_api_key, model="gpt-4o", temperature=0)


def load_farm_data():
    with open("farm_model_control.json") as f:
        farm_data = json.load(f)
    return json.dumps(farm_data["farm"]["fields"], indent=2)

farm_control_description = load_farm_data()

def get_jwt_token():
    url = f"{THINGSBOARD_URL}/api/auth/login"
    response = requests.post(url, json={"username": USERNAME, "password": PASSWORD})
    response.raise_for_status()
    return response.json()["token"]


def get_device_id_by_name(device_name, token):
    url = f"{THINGSBOARD_URL}/api/tenant/devices?deviceName={device_name}"
    headers = {"X-Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("id", {}).get("id")  # Device UUID
    else:
        raise Exception(f"Device {device_name} not found. Status: {response.status_code}")


def get_device_access_token(token, device_id):
    if not device_id:
        return None
    
    url = f"{THINGSBOARD_URL}/api/device/{device_id}/credentials"
    headers = {'Content-Type': 'application/json', 'X-Authorization': f'Bearer {token}'}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        credentials_data = response.json()
        return credentials_data.get('credentialsId')
    except requests.exceptions.RequestException as e:
        print(f"Error retrieving device credentials: {e}")
        return None

# === FUNCTION SCHEMA ===
class ActutatorExtraction(BaseModel):
    actuator_id: List[str] = Field(..., description="List of actuators IDs relevant to the query")


# def build_prompt_control(farm_control_description: str):
#     system_message = SystemMessage(
#         content=(
#             "You are a smart farm assistant. Based on the user query and this farm data, extract actuator IDs. Actuators include PUMP, DISPENSER and VALVE e.g- PUMP-0300, PUMP-0301, WV-0300, FD-0300. The pumps for water ends with `00` e.g PUMP-0300 and the pumps for fertilizer ends `01` e.g PUMP-0301 and the valves for water starts with `WV` and the valves for fertilizer start with `FD` e.g FD-0300\n"
#             "Respond ONLY with a JSON object in this format: {\"actuator_id\": [...]}\n\n"
#             f"Farm field data:\n{farm_control_description}"
#         )
#     )
#     human_message = HumanMessagePromptTemplate.from_template("{input}")
#     return ChatPromptTemplate.from_messages([system_message, human_message])

def build_prompt_control(farm_control_description: str):
    system_message = SystemMessage(
        content=(
            "You are a smart farm assistant designed to extract actuator IDs based on user queries and farm field data.\n\n"
            "Your task is to identify actuators related to WATER or FERTILIZER control. These include:\n"
            "- PUMPS: IDs like `PUMP-0300`, `PUMP-0301`  \n"
            "- VALVES: IDs like `WV-0300` (for water), `FD-0300` (for fertilizer)\n\n"
            "**Naming Conventions:**\n"
            "- PUMP-xxxx:\n"
            "  - Ends with `00` → Water pump (e.g., PUMP-0300)\n"
            "  - Ends with `01` → Fertilizer pump (e.g., PUMP-0301)\n"
            "- WV-xxxx → Water valve\n"
            "- FD-xxxx → Fertilizer valve\n\n"
            "**Instructions:**\n"
            "- Only include actuator IDs that are relevant to the query.\n"
            "- Do not include sensor IDs or unrelated components.\n"
            "- Your response must be a JSON object ONLY in the following format:\n"
            "  {\"actuator_id\": [\"PUMP-0301\", \"FD-0300\", ...]}\n\n"
            "**Farm Field Data:**\n"
            f"{farm_control_description}"
        )
    )
    human_message = HumanMessagePromptTemplate.from_template("{input}")
    return ChatPromptTemplate.from_messages([system_message, human_message])


# def control_actuator(device_name, device_state): 

#     login_url = f"{THINGSBOARD_HOST}/api/auth/login"
#     login_payload = {
#         "username": USERNAME,
#         "password": PASSWORD
#     }
#     jwt_token = get_jwt_token()
#     session = requests.Session()
#     auth_response = session.post(login_url, json=login_payload)

#     get_device_url = f"{THINGSBOARD_HOST}/api/tenant/devices?deviceName={device_name}"
#     device_response = session.get(get_device_url)
#     device_id = device_response.json().get("id", {}).get("id")

#     # Step 3: Get device credentials (includes the access token)
#     credentials_url = f"{THINGSBOARD_HOST}/api/device/{device_id}/credentials"
#     credentials_response = session.get(credentials_url)

#     access_token = credentials_response.json().get("credentialsId")
#     print(f"Access token for '{device_name}':", access_token)

#     thingsboard_url = f"http://localhost:8080/api/v1/{access_token}/telemetry"

#     # Define actuator control command (e.g., turn on/off a light)
#     payload = {
#         "deviceState": device_state  # Change this based on what your actuator expects
#     }

#     headers = {
#         "Content-Type": "application/json"
#     }

#     # Send the telemetry (command) to the device
#     response = requests.post(thingsboard_url, headers=headers, data=json.dumps(payload))

#     if response.status_code == 200:
#         print("Actuator controlled successfully!")
#     else:
#         print(f"Failed to control actuator: {response.status_code} - {response.text}")


@tool
def control_actuator(device_name: str, device_state: int) -> str:
    """Control an actuator (e.g., turn ON/OFF) by device name and desired state (1=ON, 0=OFF)."""
    try:
        jwt_token = get_jwt_token()
        device_id = get_device_id_by_name(device_name, jwt_token)
        if not device_id:
            return f"Device '{device_name}' not found."

        access_token = get_device_access_token(jwt_token, device_id)
        if not access_token:
            return f"Access token for '{device_name}' not found."

        telemetry_url = f"{THINGSBOARD_HOST}/api/v1/{access_token}/telemetry"
        payload = {"deviceState": device_state}
        headers = {"Content-Type": "application/json"}

        response = requests.post(telemetry_url, headers=headers, data=json.dumps(payload))
        if response.status_code == 200:
            return f"Successfully set state of '{device_name}' to {'ON' if device_state == 1 else 'OFF'}."
        else:
            return f"Failed to control actuator '{device_name}': {response.status_code} - {response.text}"
    except Exception as e:
        return f"Error while controlling actuator '{device_name}': {str(e)}"
    
    


# === TOOL WRAPPING ===
def build_control_extraction_tool(model, prompt_template) -> Runnable:
    runnable = create_openai_fn_runnable([ActutatorExtraction], model, prompt_template)

    @tool
    def control_extraction(input: str) -> dict:
        """Extract relevant actuator IDs from a user query about farm fields."""
        return runnable.invoke({"input": input})

    return control_extraction



prompt_control_template = build_prompt_control(farm_control_description)
control_tool = build_control_extraction_tool(model, prompt_control_template)

# control_extraction_agent= create_react_agent(
#         model=model,
#         tools=[control_tool],
#         prompt="You are an expert in identifying relevant actuator IDs from natural language farm queries.",
#         name="control_extraction_agent"
#     )

# control_extraction_agent = create_react_agent(
#     model=model,
#     tools=[control_tool, control_actuator],
#     prompt=(
#         "You are a smart farm assistant that specializes in identifying and extracting actuator IDs from natural language queries.\n\n"
#         "Your primary goal is to interpret a user's request about field operations and extract the **relevant actuator IDs** from the available farm data.\n\n"
#         "**Actuators include:**\n"
#         "- PUMPS for water or fertilizer (e.g., `PUMP-0300`, `PUMP-0301`)\n"
#         "- VALVES for water or fertilizer (e.g., `WV-0300`, `FD-0300`)\n\n"
#         "**Naming conventions:**\n"
#         "- `PUMP-xxxx`\n"
#         "   - Ends with `00` → Water pump\n"
#         "   - Ends with `01` → Fertilizer pump\n"
#         "- `WV-xxxx` → Water valves\n"
#         "- `FD-xxxx` → Fertilizer valves\n\n"
#         "**Your task:**\n"
#         "- Read the user query carefully.\n"
#         "- Determine if the user is referring to fertilizer or water.\n"
#         "- Identify the relevant actuator types (pump/valve) based on function.\n"
#         "- Use the provided tool to extract and return only the correct actuator IDs.\n\n"
#         "**Output format:**\n"
#         "Return the result in a valid JSON object: {\"actuator_id\": [\"ACTUATOR_ID1\", \"ACTUATOR_ID2\", ...]}\n\n"
#         "You must use the tool provided to accomplish this task. Do not generate actuator IDs yourself."
#         "Finally, use the extracted actuactor name to control a the actuator by passing the  actuator name desire state State (ON/OFF). Note ON - 1 and OFF - 0"
#     ),
#     name="control_extraction_agent"
# )


control_extraction_agent = create_react_agent(
    model=model,
    tools=[control_tool, control_actuator],
    prompt=(
        "You are a smart farm assistant specializing in identifying and extracting actuator IDs from natural language queries.\n\n"
        "Your primary goal is to understand a user's request about field operations and extract the correct **actuator IDs** using the provided tools.\n\n"
        "### 🔧 Actuator Types:\n"
        "- **PUMPS** for water or fertilizer (e.g., `PUMP-0300`, `PUMP-0301`)\n"
        "- **VALVES** for water or fertilizer (e.g., `WV-0300`, `FD-0300`)\n\n"
        "### 🧭 Naming Conventions:\n"
        "- `PUMP-xxxx`\n"
        "   - Ends in `00` → Water pump\n"
        "   - Ends in `01` → Fertilizer pump\n"
        "- `WV-xxxx` → Water valves\n"
        "- `FD-xxxx` → Fertilizer valves\n\n"
        "### 🧠 Your Task:\n"
        "1. Read and understand the user query.\n"
        "2. Determine whether the request is about **water** or **fertilizer**.\n"
        "3. Identify the correct actuator types (**pump** or **valve**).\n"
        "4. Use the `control_tool` to extract relevant actuator IDs from available farm data.\n"
        "5. Use the `control_actuator` tool to apply the desired action (turn ON/OFF).\n\n"
        "### 📤 Output Format:\n"
        "Return the result as a JSON object in this format:\n"
        "`{\"actuator_ids\": [\"ACTUATOR_ID1\", \"ACTUATOR_ID2\", ...]}`\n\n"
        "⚠️ Do not make up actuator IDs. You must use the provided `control_tool` to extract them.\n"
        "⚠️ To control an actuator, use the `control_actuator` tool with the actuator name and desired state:\n"
        "- `1` = ON\n"
        "- `0` = OFF"
    ),
    name="control_extraction_agent"
)


# input_query = "Get all actuators  for water in central field."
# input_query = "Turn off the water pump in the West  field."
# input_query = "Turn off South field fertilizer dispenser."
# inputs = {"messages": [HumanMessage(content=input_query)]}
# result = control_extraction_agent.invoke(inputs)

# # Print result
# for msg in result["messages"]:
#     msg.pretty_print()


