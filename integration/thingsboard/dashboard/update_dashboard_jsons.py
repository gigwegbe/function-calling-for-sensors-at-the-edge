import json
import csv
import os

# Paths to the current folder and the merged CSV file
current_folder = os.path.dirname(__file__)  # Get the folder where the script is located
merged_csv_path = os.path.join(current_folder, "widget_device_mapping.csv")  # Relative path to the merged CSV file

# Load the merged CSV file
widget_device_mapping = {}
with open(merged_csv_path, "r") as csv_file:
    csv_reader = csv.DictReader(csv_file)
    for row in csv_reader:
        widget_device_mapping[row["Widget Name"]] = {
            "deviceName": row["Device Name"],
            "deviceId": row["Device ID"]
        }

# Iterate through all JSON files in the current folder
for filename in os.listdir(current_folder):
    if filename.endswith(".json"):
        json_file_path = os.path.join(current_folder, filename)

        # Load the JSON file
        with open(json_file_path, "r") as json_file:
            dashboard_data = json.load(json_file)

        # Update the JSON file
        widgets = dashboard_data.get("configuration", {}).get("widgets", {})
        for widget_id, widget in widgets.items():
            title = widget.get("config", {}).get("title")
            if title in widget_device_mapping:
                device_info = widget_device_mapping[title]
                device_name = device_info["deviceName"]
                device_id = device_info["deviceId"]

                # Check if the widget is map-based
                if widget.get("typeFullFqn", "").startswith("system.maps"):
                    # For map-based widgets, update multiple datasources
                    for datasource in widget.get("config", {}).get("datasources", []):
                        # Update only the deviceId for map-based widgets
                        datasource["deviceId"] = device_id
                else:
                    # For non-map-based widgets, update both deviceName and deviceId
                    for datasource in widget.get("config", {}).get("datasources", []):
                        datasource["name"] = device_name
                        datasource["deviceId"] = device_id

        # Save the updated JSON file
        with open(json_file_path, "w") as json_file:
            json.dump(dashboard_data, json_file, indent=2)

        print(f"Updated {json_file_path} with device names and IDs from {merged_csv_path}.")