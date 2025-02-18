import paho.mqtt.client as mqtt
import json
import time
import random
import threading

THINGSBOARD_HOST = "localhost"  # Change if using a remote server

# Device Tokens (Replace these with your actual device tokens)
DEVICES = {
    "sectionA1": "3q4fpldyoav8h4p0812k",
    "sectionA2": "i69d6wwfyptbrghs9lxj",
}

# Function to send telemetry for a device
def send_telemetry(device_name, token):
    client = mqtt.Client()
    client.username_pw_set(token)
    client.connect(THINGSBOARD_HOST, 1883, 60)
    
    print(f"Started {device_name} telemetry...")
    
    try:
        while True:
            if device_name == "sectionA1":
                temperature = round(random.uniform(20, 30), 2)  # Simulated temperature
                humidity = round(random.uniform(40, 70), 2)  # Simulated humidity
                payload = {"sectionA1": temperature, "sectionA2": humidity}
            
            else:
                # Default telemetry in case device_name is unknown
                payload = {"message": "Unknown device"}


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








import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import paho.mqtt.client as mqtt
import json
import time
import threading
from typing import Dict

class ThingsboardFarmSensor:
    def __init__(self, sensor_id: str, token: str, host: str = "localhost"):
        self.sensor_id = sensor_id
        self.simulator = FarmSensorSimulator(
            start_date=datetime.now().strftime("%Y-%m-%d"),
            end_date=(datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
            sensor_id=sensor_id
        )
        
        # MQTT client setup
        self.client = mqtt.Client()
        self.client.username_pw_set(token)
        self.client.connect(host, 1883, 60)
        self.running = True

    def generate_current_reading(self) -> Dict:
        """Generate a single reading for the current timestamp"""
        current_time = pd.Timestamp.now()
        
        # Generate single readings using simulator methods
        moisture = float(self.simulator.simulate_soil_moisture(pd.DatetimeIndex([current_time]))[0])
        temperature = float(self.simulator.simulate_soil_temperature(pd.DatetimeIndex([current_time]))[0])
        ec = float(self.simulator.simulate_soil_ec(np.array([moisture]))[0])
        battery = float(self.simulator.simulate_battery_level(pd.DatetimeIndex([current_time]))[0])
        
        return {
            "soil_moisture": round(moisture, 2),
            "soil_temperature": round(temperature, 2),
            "soil_electrocoductivity": round(ec, 2),
            "battery_level": round(battery, 2)
        }

    def run(self, interval: float = 2.0):
        """Run continuous data transmission"""
        print(f"Started {self.sensor_id} telemetry...")
        
        while self.running:
            try:
                # Generate and send data
                payload = self.generate_current_reading()
                payload_json = json.dumps(payload)
                self.client.publish("v1/devices/me/telemetry", payload_json)
                print(f"{self.sensor_id} Sent: {payload_json}")
                
                time.sleep(interval)
                
            except Exception as e:
                print(f"Error in {self.sensor_id}: {str(e)}")
                time.sleep(5)  # Wait before retrying
                
        self.client.disconnect()

    def stop(self):
        """Stop the sensor transmission"""
        self.running = False

def run_farm_section(section_config: Dict[str, str], host: str = "localhost"):
    """
    Run multiple sensors for a farm section
    
    Args:
        section_config: Dictionary mapping sensor IDs to their ThingsBoard access tokens
        host: ThingsBoard host address
    """
    sensors = []
    threads = []
    
    # Create and start each sensor
    for sensor_id, token in section_config.items():
        sensor = ThingsboardFarmSensor(sensor_id, token, host)
        sensors.append(sensor)
        
        thread = threading.Thread(target=sensor.run)
        thread.start()
        threads.append(thread)
    
    try:
        # Wait for all threads
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        print("Stopping all sensors...")
        for sensor in sensors:
            sensor.stop()

if __name__ == "__main__":
    # Example configuration
    THINGSBOARD_HOST = "localhost"
    DEVICES = {
        "A101": "3q4fpldyoav8h4p0812k",
        "A102": "i69d6wwfyptbrghs9lxj",
    }
    
    # Run the farm section
    run_farm_section(DEVICES, THINGSBOARD_HOST)
