from flask import Flask, render_template, request, jsonify
from flask_cors import CORS  # Import flask_cors
import paho.mqtt.client as mqtt
import json
import time
import random
import threading
import logging

app = Flask(__name__)

# Enable CORS for all origins (no restrictions)
CORS(app)  # This will allow all domains to access the API

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Global variables
active_threads = {}
THINGSBOARD_HOST = os.getenv('THINGSBOARD_HOST', 'localhost')

def send_telemetry(device_name, token):
    client = mqtt.Client(protocol=mqtt.MQTTv311)
    client.username_pw_set(token)
    
    try:
        client.connect(THINGSBOARD_HOST, 1883, 60)
        client.loop_start()
        logging.info(f"[{device_name}] Connected to ThingsBoard")
        
        while not threading.current_thread().stop_flag:
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/start', methods=['POST'])
def start_device():
    data = request.get_json()
    device_name = data.get('name')
    token = data.get('token')
    
    if device_name in active_threads:
        return jsonify({"error": "Device already running"}), 400
    
    thread = threading.Thread(target=send_telemetry, args=(device_name, token))
    thread.stop_flag = False
    thread.start()
    active_threads[device_name] = thread
    
    return jsonify({"message": f"Started {device_name}"}), 200

@app.route('/api/stop', methods=['POST'])
def stop_device():
    data = request.get_json()
    device_name = data.get('name')
    
    if device_name not in active_threads:
        return jsonify({"error": "Device not running"}), 400
    
    active_threads[device_name].stop_flag = True
    active_threads[device_name].join()
    del active_threads[device_name]
    
    return jsonify({"message": f"Stopped {device_name}"}), 200

@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({
        "active_devices": list(active_threads.keys())
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
