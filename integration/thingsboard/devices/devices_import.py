import json
import requests


# ThingsBoard server details
TB_URL = "http://localhost:8080"
ACCESS_TOKEN = "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJ0ZW5hbnRAdGhpbmdzYm9hcmQub3JnIiwid>

# Load the exported devices JSON
with open("devices_export.json", "r") as file:
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
        headers={"Content-Type": "application/json", "X-Authorization": f"Bearer {>
        json=payload,
    )

    if response.status_code == 200:
        print(f"✅ Device '{device['name']}' imported successfully!")
    else:
        print(f"❌ Failed to import '{device['name']}': {response.text}")