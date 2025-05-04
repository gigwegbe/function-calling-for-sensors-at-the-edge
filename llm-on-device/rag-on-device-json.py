import json
import requests

# Load the JSON file
with open("farm_model_control.json", "r") as file:
    control_data = json.load(file)

# Format the prompt
# prompt = f"""
# This JSON describes the control structure of a smart farm, including fields and their actuators.

# Please summarize the types of actuators and list which fields use which actuators.

# JSON:
# {json.dumps(control_data, indent=2)}
# """
prompt = f"""
This JSON describes the control structure of a smart farm, including fields and their actuators.

# Please summarize the pumps in Central  field.

JSON:
{json.dumps(control_data, indent=2)}
"""

# Send request to LLaMA 3:8B via Ollama
response = requests.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "qwen2.5:14b",
        "prompt": prompt,
        "stream": False
    }
)

# Print the response or error
try:
    result = response.json()
    print(result.get("response", "No 'response' key found. Full output:\n" + str(result)))
except json.JSONDecodeError:
    print("Failed to decode JSON from response:")
    print(response.text)
