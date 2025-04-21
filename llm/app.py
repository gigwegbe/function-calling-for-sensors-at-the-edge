from flask import Flask, render_template, request, redirect, jsonify
import requests
import time
# import psycopg2

external_scripts = [
    {'src': 'http://localhost:8000/copilot/index.js'}
]


app = Flask(__name__)
# ThingsBoard settings
THINGSBOARD_URL = "http://localhost:8080"
USERNAME = "tenant@thingsboard.org"
PASSWORD = "tenant"
DASHBOARD_ID = "http://localhost:8080/tenants"

DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "thingsboard"
DB_USER = "thingsboard"
DB_PASSWORD = "postgres"


DEVICE_ID = "708e8b40-eddd-11ef-8ae3-c317086909d8"



def get_jwt_token():
    url = f"{THINGSBOARD_URL}/api/auth/login"
    payload = {
        "username": USERNAME,
        "password": PASSWORD
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        return response.json().get("token")
    else:
        print("Failed to authenticate:", response.text)
        return None


@app.route('/')
def home():
    jwt_token = get_jwt_token()
    print(jwt_token)
    if jwt_token:
        dashboard_url = DASHBOARD_ID
        return render_template('dashboard.html', dashboard_url=dashboard_url, jwt_token=jwt_token)
    else:
        return "Failed to authenticate with ThingsBoard", 401


# Fetch last 24 hours of telemetry data
@app.route('/realtime-telemetry')
def historical_telemetry():
    jwt_token = get_jwt_token()
    if not jwt_token:
        return jsonify({"error": "Authentication failed"}), 401

    # Last 24 hours timestamps
    end_ts = int(time.time() * 1000)  
    start_ts = end_ts - (24 * 60 * 60 * 1000)  # 24 hours ago
    

    keys = "temperature"  

    data = get_historical_data(jwt_token, DEVICE_ID, start_ts, end_ts, keys)
    return jsonify(data)


def get_historical_data(jwt_token, device_id, start_ts, end_ts, keys):
    url = f"{THINGSBOARD_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
    params = {"keys": keys, "startTs": start_ts, "endTs": end_ts, "limit": 1000}
    headers = {"X-Authorization": f"Bearer {jwt_token}"}
    
    response = requests.get(url, headers=headers, params=params)
    return response.json() if response.status_code == 200 else {"error": "Failed to fetch telemetry data"}


if __name__ == '__main__':
    app.run(debug=True)

