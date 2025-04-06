import paho.mqtt.client as mqtt
import json
import time
import random
import threading
import os
import logging
import argparse

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

THINGSBOARD_HOST = os.getenv('THINGSBOARD_HOST', 'localhost')

# Default device tokens
DEFAULT_DEVICES = {
    "temperature_sensor": "AflZM8FbdYZjvJw1PqaL",
    "soil_moisture_sensor": "iTpodQOhI19yzZbjtzYa",
}

# Parse command-line arguments
parser = argparse.ArgumentParser(description="MQTT Telemetry Simulator")
parser.add_argument("--devices", nargs="+", help="List of devices in 'name:token' format")
args = parser.parse_args()

# Convert arguments to a dictionary {device_name: token}, or use default
DEVICES = {}
if args.devices:
    for device in args.devices:
        try:
            name, token = device.split(":")
            DEVICES[name] = token
        except ValueError:
            logging.error(f"Invalid device format: {device}. Expected 'name:token'.")
            exit(1)
else:
    DEVICES = DEFAULT_DEVICES  # Use default if no arguments are passed
    logging.info("No devices provided, using default devices.")

# Function to send telemetry for a device
def send_telemetry(device_name, token):
    client = mqtt.Client(protocol=mqtt.MQTTv311)
    client.username_pw_set(token)

    try:
        client.connect(THINGSBOARD_HOST, 1883, 60)
        client.loop_start()
        logging.info(f"[{device_name}] Connected to ThingsBoard")

        while True:
            try:
                if device_name == "temperature_sensor":
                    payload = {
                        "temperature": round(random.uniform(20, 30), 2),
                        "humidity": round(random.uniform(40, 70), 2),
                    }
                elif device_name == "soil_moisture_sensor":
                    payload = {"soil_moisture": round(random.uniform(30, 80), 2)}
                else:
                    payload = {"status": "unknown_device"}

                payload_json = json.dumps(payload)
                result = client.publish("v1/devices/me/telemetry", payload_json)

                if result.rc != mqtt.MQTT_ERR_SUCCESS:
                    logging.error(f"[{device_name}] Failed to publish: {payload_json}")

                logging.info(f"[{device_name}] Sent: {payload_json}")
                time.sleep(2)

            except Exception as e:
                logging.error(f"[{device_name}] Error in telemetry loop: {str(e)}")
                time.sleep(5)

    except Exception as e:
        logging.error(f"[{device_name}] Connection failed: {str(e)}")

    finally:
        client.loop_stop()
        client.disconnect()
        logging.info(f"[{device_name}] Disconnected")

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
    logging.info("Stopping all devices...")