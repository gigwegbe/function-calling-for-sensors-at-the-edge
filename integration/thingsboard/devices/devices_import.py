import json
import requests


# ThingsBoard server details
TB_URL = "http://localhost:8080"
ACCESS_TOKEN = "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJ0ZW5hbnRAdGhpbmdzYm9hcmQub3JnIiwidXNlcklkIjoiN2YzNzg0MzAtMGQ2OC0xMWYwLTk3ZGUtMDdlNDdmZjVlYWU3Iiwic2NvcGVzIjpbIlRFTkFOVF9BRE1JTiJdLCJzZXNzaW9uSWQiOiI5OTZkY2MzYi1jNDU4LTRjZTAtYjlmNy1iMGNhOGQzZmI5ZjIiLCJleHAiOjE3NDMzNTg4NTQsImlzcyI6InRoaW5nc2JvYXJkLmlvIiwiaWF0IjoxNzQzMzQ5ODU0LCJlbmFibGVkIjp0cnVlLCJpc1B1YmxpYyI6ZmFsc2UsInRlbmFudElkIjoiN2ViOTUzODAtMGQ2OC0xMWYwLTk3ZGUtMDdlNDdmZjVlYWU3IiwiY3VzdG9tZXJJZCI6IjEzODE0MDAwLTFkZDItMTFiMi04MDgwLTgwODA4MDgwODA4MCJ9.YLguaiNlJvtvsZzqczYI7cbZeBuMOqFnKpdvjbIY53okkNT-yQwjq3O_QUKiqMWxK_i0mGG36fdCF8X-Fwwh5Q"

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
        headers={"Content-Type": "application/json", "X-Authorization": f"Bearer {ACCESS_TOKEN}"},
        json=payload,
    )

    if response.status_code == 200:
        print(f"✅ Device '{device['name']}' imported successfully!")
    else:
        print(f"❌ Failed to import '{device['name']}': {response.text}")