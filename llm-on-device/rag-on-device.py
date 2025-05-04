import yaml
import requests

# Load the YAML file
with open("farm_model_control.yaml", "r") as file:
    control_data = yaml.safe_load(file)

# # Format the prompt
# prompt = f"""
# Here is a YAML file describing the control structure of a smart farm with fields and actuators:

# {yaml.dump(control_data, sort_keys=False)}

# Can you summarize the types of actuators used and which fields they are used in?
# """


# Format the prompt
prompt = f"""
Here is a YAML file describing the control structure of a smart farm with fields and actuators:

{yaml.dump(control_data, sort_keys=False)}

What water pump system in the Fields? Do no forget to the valve. Do not invent any actuator and code. Return it in json format
"""

# Send to Ollama
response = requests.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "llama3.2",
        "prompt": prompt,
        "stream": False
    }
)

# Check and handle response
if response.status_code == 200:
    data = response.json()
    if "response" in data:
        print(data["response"])
    else:
        print("No 'response' key found in:", data)
else:
    print(f"Error {response.status_code}: {response.text}")
