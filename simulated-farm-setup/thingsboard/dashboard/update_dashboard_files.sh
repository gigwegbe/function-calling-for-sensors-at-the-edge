#!/bin/bash

# Ensure all scripts are executable
chmod +x get_token.sh
chmod +x get_device_name_and_id.py
chmod +x merge_device_info.py
chmod +x update_dashboard_jsons.py

# Step 1: Run get_token.sh and capture the token
echo "Fetching ThingsBoard API token..."
ACCESS_TOKEN=$(bash get_token.sh)

# Check if the token was successfully retrieved
if [ -z "$ACCESS_TOKEN" ]; then
    echo "Failed to retrieve the API token. Exiting."
    exit 1
fi
echo "Token retrieved: $ACCESS_TOKEN"

# Step 2: Run get_device_name_and_id.py with the token
echo "Fetching device names and IDs..."
python3 get_device_name_and_id.py "$ACCESS_TOKEN"

# Check if the device-to-deviceId CSV file was created
if [ ! -f "./device_to_deviceId.csv" ]; then
    echo "Failed to fetch device names and IDs. Exiting."
    exit 1
fi
echo "Device names and IDs fetched successfully."

# Step 3: Run merge_device_info.py
echo "Merging widget and device information..."
python3 merge_device_info.py

# Check if the merged CSV file was created
if [ ! -f "./widget_device_mapping.csv" ]; then
    echo "Failed to merge widget and device information. Exiting."
    exit 1
fi
echo "Widget and device information merged successfully."

# Step 4: Run update_dashboard_jsons.py
echo "Updating dashboard JSON files..."
python3 update_dashboard_jsons.py

echo "All tasks completed successfully."