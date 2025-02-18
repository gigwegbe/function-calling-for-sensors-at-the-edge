import os
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import paho.mqtt.client as mqtt
import json
import time
import random
import threading
import logging
from dataclasses import dataclass
from typing import Dict, Any, Callable

# Data structure for device configuration
@dataclass
class DeviceConfig:
    name: str
    token: str
    data_type: str
    telemetry_function: Callable[[], Dict[str, float]]
    metrics: list[Dict[str, str]]  # Changed to support key and unit (metric)

class DeviceManager:
    def __init__(self, host: str):
        self.host = host
        self.active_threads: Dict[str, threading.Thread] = {}
        self.devices: Dict[str, DeviceConfig] = {}
        self.logger = logging.getLogger(__name__)

    def register_device(self, name: str, token: str, data_type: str, telemetry_function: Callable[[], Dict[str, float]], metrics: list[Dict[str, str]]):
        """Register a new device with the manager"""
        self.devices[name] = DeviceConfig(
            name=name,
            token=token,
            data_type=data_type,
            telemetry_function=telemetry_function,
            metrics=metrics
        )
        self.logger.info(f"Registered device: {name} of type {data_type}")

    def send_telemetry(self, device_name: str):
        """Send telemetry data for a specific device"""
        device = self.devices[device_name]
        client = mqtt.Client(protocol=mqtt.MQTTv311)
        client.username_pw_set(device.token)

        try:
            client.connect(self.host, 1883, 60)
            client.loop_start()
            self.logger.info(f"[{device_name}] Connected to ThingsBoard")

            while not threading.current_thread().stop_flag:
                try:
                    payload = device.telemetry_function()
                    payload_json = json.dumps(payload)
                    result = client.publish("v1/devices/me/telemetry", payload_json)
                    
                    if result.rc != mqtt.MQTT_ERR_SUCCESS:
                        self.logger.error(f"[{device_name}] Failed to publish: {payload_json}")
                    else:
                        self.logger.info(f"[{device_name}] Sent: {payload_json}")
                    
                    time.sleep(2)
                except Exception as e:
                    self.logger.error(f"[{device_name}] Error in telemetry loop: {str(e)}")
                    time.sleep(5)

        except Exception as e:
            self.logger.error(f"[{device_name}] Connection failed: {str(e)}")
        finally:
            client.loop_stop()
            client.disconnect()
            self.logger.info(f"[{device_name}] Disconnected")

    def start_device(self, name: str) -> bool:
        """Start a device's telemetry transmission"""
        if name not in self.devices:
            return False
        if name in self.active_threads:
            return False

        thread = threading.Thread(target=self.send_telemetry, args=(name,))
        thread.stop_flag = False
        thread.start()
        self.active_threads[name] = thread
        return True

    def stop_device(self, name: str) -> bool:
        """Stop a device's telemetry transmission"""
        if name not in self.active_threads:
            return False

        self.active_threads[name].stop_flag = True
        self.active_threads[name].join()
        del self.active_threads[name]
        return True

    def get_active_devices(self) -> list:
        """Get list of currently active devices"""
        return list(self.active_threads.keys())

    def get_all_devices(self) -> list:
        """Get list of all registered devices"""
        return [{"name": name, "type": device.data_type, "metrics": device.metrics} 
                for name, device in self.devices.items()]

# Initialize Flask app and device manager
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
device_manager = DeviceManager(os.getenv('THINGSBOARD_HOST', 'localhost'))

def create_generic_telemetry(metrics):
    """Creates a telemetry function for arbitrary metrics with random values"""
    def telemetry_function():
        return {metric['name']: round(random.uniform(0, 100), 2) for metric in metrics}
    return telemetry_function

# Example telemetry functions
def temperature_telemetry():
    return {
        "temperature": round(random.uniform(20, 30), 2),
        "humidity": round(random.uniform(40, 70), 2)
    }

def soil_moisture_telemetry():
    return {
        "soil_moisture": round(random.uniform(30, 80), 2)
    }

# Register default devices
device_manager.register_device(
    name="temperature_sensor",
    token="",
    data_type="temperature",
    telemetry_function=temperature_telemetry,
    metrics=[{"name": "temperature", "unit": "°C"}, {"name": "humidity", "unit": "%"}]
)

device_manager.register_device(
    name="soil_moisture_sensor",
    token="",
    data_type="soil_moisture",
    telemetry_function=soil_moisture_telemetry,
    metrics=[{"name": "soil_moisture", "unit": "%"}]
)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/devices', methods=['GET'])
def get_devices():
    return jsonify({"devices": device_manager.get_all_devices()})

@app.route('/api/devices/create', methods=['POST'])
def create_device():
    data = request.get_json()
    name = data.get('name')
    data_type = data.get('type')
    metrics = data.get('metrics', [])
    
    if not name or not data_type or not metrics:
        return jsonify({"error": "Missing required fields"}), 400
    
    if name in device_manager.devices:
        return jsonify({"error": "Device name already exists"}), 400
    
    try:
        telemetry_function = create_generic_telemetry(metrics)
        device_manager.register_device(
            name=name,
            token="",
            data_type=data_type,
            telemetry_function=telemetry_function,
            metrics=metrics
        )
        return jsonify({"message": f"Device {name} created successfully"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

@app.route('/api/devices/<device_name>', methods=['DELETE'])
def delete_device(device_name):
    """Delete a device by its name"""
    if device_name not in device_manager.devices:
        return jsonify({"error": "Device not found"}), 404

    # Stop the device if it's active
    device_manager.stop_device(device_name)
    
    # Remove the device from the devices list
    del device_manager.devices[device_name]
    
    return jsonify({"message": f"Device {device_name} deleted successfully"}), 200


@app.route('/api/start', methods=['POST'])
def start_device():
    data = request.get_json()
    device_name = data.get('name')
    token = data.get('token')
    
    if not device_name or not token:
        return jsonify({"error": "Missing device name or token"}), 400
    
    if device_name not in device_manager.devices:
        return jsonify({"error": "Unknown device"}), 404
        
    device_manager.devices[device_name].token = token
    
    if device_manager.start_device(device_name):
        return jsonify({"message": f"Started {device_name}"}), 200
    else:
        return jsonify({"error": "Device already running"}), 400

@app.route('/api/stop', methods=['POST'])
def stop_device():
    data = request.get_json()
    device_name = data.get('name')
    
    if not device_name:
        return jsonify({"error": "Missing device name"}), 400
        
    if device_manager.stop_device(device_name):
        return jsonify({"message": f"Stopped {device_name}"}), 200
    else:
        return jsonify({"error": "Device not running"}), 400

@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({
        "active_devices": device_manager.get_active_devices()
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
