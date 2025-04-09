from flask import Flask, jsonify
import requests
import time

app = Flask(__name__)

# ThingsBoard settings
THINGSBOARD_URL = "http://localhost:8080"
USERNAME = "tenant@thingsboard.org"
PASSWORD = "tenant"
DEVICE_ID = "708e8b40-eddd-11ef-8ae3-c317086909d8"

# Threshold values and alert messages
THRESHOLDS = {
    "soil_temperature": {
        "critical": (10, 35),
        "warning": (18, 30),
        "messages": {
            "critical_low": "Potential frost risk! Soil temperature below 10°C.",
            "critical_high": "Risk of crop stress! Soil temperature above 35°C.",
            "warning_low": "Soil temperature below normal range.",
            "warning_high": "Soil temperature above normal range."
        }
    },
    "soil_moisture": {
        "critical": (10, 70),
        "warning": (20, 60),
        "messages": {
            "critical_low": "Soil is extremely dry! Activate irrigation pumps.",
            "critical_high": "Risk of waterlogging! Reduce irrigation.",
            "warning_low": "Soil is too dry, consider irrigation.",
            "warning_high": "Soil is too wet, reduce irrigation."
        }
    },
    "soil_conductivity": {
        "critical": (30, 300),
        "warning": (50, 250),
        "messages": {
            "critical_low": "Nutrient depletion! Suggest fertilization.",
            "critical_high": "Excess fertilizers or salt accumulation! Suggest soil flushing.",
            "warning_low": "Low nutrient levels detected.",
            "warning_high": "High conductivity levels detected."
        }
    },
    "plant_health": {
        "critical": (50, 100),
        "warning": (75, 100),
        "messages": {
            "critical_low": "Plant health critically low! Inspect manually.",
            "warning_low": "Plant health below normal range."
        }
    },
    "battery_level": {
        "critical": (5, 100),
        "warning": (30, 100),
        "messages": {
            "critical_low": "Battery critically low! Switch to backup battery.",
            "warning_low": "Battery low! Trigger low-power mode."
        }
    }
}

def get_jwt_token():
    url = f"{THINGSBOARD_URL}/api/auth/login"
    payload = {"username": USERNAME, "password": PASSWORD}
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        return response.json().get("token")
    else:
        print("Failed to authenticate:", response.text)
        return None

def get_recent_telemetry(jwt_token, device_id, minutes=10):
    end_ts = int(time.time() * 1000)
    start_ts = end_ts - (minutes * 60 * 1000)
    keys = "temperature,humidity,conductivity,moisture,plant_health,battery_level"

    url = f"{THINGSBOARD_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
    params = {"keys": keys, "startTs": start_ts, "endTs": end_ts, "limit": 1000}
    headers = {"X-Authorization": f"Bearer {jwt_token}"}

    response = requests.get(url, headers=headers, params=params)
    return response.json() if response.status_code == 200 else {"error": "Failed to fetch telemetry data"}

def check_thresholds(telemetry_data):
    alerts = []
    for data in telemetry_data:
        sensor_type = data.get("key")
        value = data.get("value")

        if sensor_type in THRESHOLDS:
            warning_range = THRESHOLDS[sensor_type]["warning"]
            critical_range = THRESHOLDS[sensor_type]["critical"]
            messages = THRESHOLDS[sensor_type]["messages"]

            if value < critical_range[0]:
                alerts.append(messages["critical_low"])
            elif value > critical_range[1]:
                alerts.append(messages["critical_high"])
            elif value < warning_range[0]:
                alerts.append(messages["warning_low"])
            elif value > warning_range[1]:
                alerts.append(messages["warning_high"])

    return alerts

@app.route('/check-alerts', methods=['GET'])
def check_alerts():
    jwt_token = get_jwt_token()
    if not jwt_token:
        return jsonify({"error": "Authentication failed"}), 401

    telemetry_data = get_recent_telemetry(jwt_token, DEVICE_ID)
    if "error" in telemetry_data:
        return jsonify(telemetry_data), 500

    alerts = check_thresholds(telemetry_data)
    return jsonify({"alerts": alerts})

if __name__ == '__main__':
    app.run(debug=True)
