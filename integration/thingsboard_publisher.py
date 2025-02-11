import paho.mqtt.client as mqtt
import json
import time
import random
import threading

THINGSBOARD_HOST = "localhost"  # Change if using a remote server

# Device Tokens (Replace these with your actual device tokens)
DEVICES = {
    "temperature_sensor": "3uvhmtqusaj25n1g3vht",
    "soil_moisture_sensor": "OOsPmSYVks52IsyuK7va",
}

# Function to send telemetry for a device
def send_telemetry(device_name, token):
    client = mqtt.Client()
    client.username_pw_set(token)
    client.connect(THINGSBOARD_HOST, 1883, 60)
    
    print(f"Started {device_name} telemetry...")
    
    try:
        while True:
            if device_name == "temperature_sensor":
                temperature = round(random.uniform(20, 30), 2)  # Simulated temperature
                humidity = round(random.uniform(40, 70), 2)  # Simulated humidity
                payload = {"temperature": temperature, "humidity": humidity}
            
            elif device_name == "soil_moisture_sensor":
                soil_moisture = round(random.uniform(30, 80), 2)  # Simulated soil moisture
                payload = {"soil_moisture": soil_moisture}

            # Convert to JSON
            payload_json = json.dumps(payload)
            client.publish("v1/devices/me/telemetry", payload_json)
            
            print(f"{device_name} Sent: {payload_json}")
            time.sleep(2)  # Send data every 2 seconds

    except KeyboardInterrupt:
        print(f"Stopped {device_name} telemetry")
        client.disconnect()

# Start threads for each device
threads = []
for device_name, token in DEVICES.items():
    thread = threading.Thread(target=send_telemetry, args=(device_name, token))
    thread.start()
    threads.append(thread)

# Keep main thread running
try:
    for thread in threads:
        thread.join()
except KeyboardInterrupt:
    print("Stopping all devices...")