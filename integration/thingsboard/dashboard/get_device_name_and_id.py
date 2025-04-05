import requests
import csv
import sys

# Get the token from the command-line argument
if len(sys.argv) < 2:
    print("Usage: python3 get_device_name_and_id.py <ACCESS_TOKEN>")
    sys.exit(1)

ACCESS_TOKEN = sys.argv[1]

# ThingsBoard API URL
THINGSBOARD_URL = "http://localhost:8080"  # Replace with your ThingsBoard URL

# API endpoint to fetch devices
API_ENDPOINT = f"{THINGSBOARD_URL}/api/tenant/devices?pageSize=1000&page=0"

# HTTP headers for authentication
headers = {
    "Content-Type": "application/json",
    "X-Authorization": f"Bearer {ACCESS_TOKEN}"
}

# Output CSV file path
output_csv_path = "./device_to_deviceId.csv"  # Replace with the desired output file path

# Fetch devices from ThingsBoard
response = requests.get(API_ENDPOINT, headers=headers)

if response.status_code == 200:
    devices = response.json().get("data", [])
    # Write devices to CSV
    with open(output_csv_path, mode="w", newline="") as csv_file:
        csv_writer = csv.writer(csv_file)
        # Write header row
        csv_writer.writerow(["Device Name", "Device ID"])
        # Write device data
        for device in devices:
            csv_writer.writerow([device["name"], device["id"]["id"]])
    print(f"Device data has been written to {output_csv_path}.")
else:
    print(f"Failed to fetch devices. Status Code: {response.status_code}, Response: {response.text}")