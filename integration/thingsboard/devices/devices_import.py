import json
import requests
import sys


# ThingsBoard server details
TB_URL = "http://localhost:8080"

# Get the access token from the command-line argument
if len(sys.argv) < 2:
    print("Usage: python3 devices_import.py <ACCESS_TOKEN>")
    sys.exit(1)

ACCESS_TOKEN = sys.argv[1]

# Load the exported devices JSON
with open("devices.json", "r") as file:
    data = json.load(file)

devices = data.get("data", [])

for device in devices:
    payload = {
        "name": device["name"],
        "type": device["type"],
        "label": device.get("label", ""),
        "additionalInfo": device.get("additionalInfo", {}),
    }

    response = requests.post(
        f"{TB_URL}/api/device",
        headers={"Content-Type": "application/json", "X-Authorization": f"Bearer {ACCESS_TOKEN}"},
        json=payload,
    )

    if response.status_code == 200:
        print(f"✅ Device '{device['name']}' imported successfully!")
    else:
        print(f"❌ Failed to import '{device['name']}': {response.text}")