import csv

# File paths
widget_to_device_csv = "./widget_data_sources.csv"  # Replace with the path to the widget-to-device mapping CSV
device_to_deviceId_csv = "./device_to_deviceId.csv"  # Replace with the path to the device-to-deviceId mapping CSV
output_csv = "./widget_device_mapping.csv"  # Replace with the desired output file path

# Load device-to-deviceId mapping into a dictionary
device_to_deviceId = {}
with open(device_to_deviceId_csv, mode="r") as device_file:
    csv_reader = csv.DictReader(device_file)
    for row in csv_reader:
        device_to_deviceId[row["Device Name"]] = row["Device ID"]

# Merge widget-to-device mapping with device-to-deviceId mapping
with open(widget_to_device_csv, mode="r") as widget_file, open(output_csv, mode="w", newline="") as output_file:
    widget_reader = csv.DictReader(widget_file)
    output_writer = csv.writer(output_file)

    # Write header row
    output_writer.writerow(["Widget Name", "Device Name", "Device ID"])

    # Write merged data
    for row in widget_reader:
        widget_name = row["Widget Name"]
        device_name = row["Device Name"]
        device_id = device_to_deviceId.get(device_name, "Not Found")  # Handle missing device IDs
        output_writer.writerow([widget_name, device_name, device_id])

print(f"Merged data has been written to {output_csv}.")