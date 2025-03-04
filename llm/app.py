from flask import Flask, render_template, request, jsonify
import requests
import time
import psycopg2
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ThingsBoard settings
THINGSBOARD_URL = "http://localhost:8080"
USERNAME = "tenant@thingsboard.org"
PASSWORD = "tenant"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "thingsboard"
DB_USER = "thingsboard"
DB_PASSWORD = "postgres"

# Connect to the database
def get_db_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    return conn

# Authenticate with ThingsBoard
def get_jwt_token():
    url = f"{THINGSBOARD_URL}/api/auth/login"
    payload = {"username": USERNAME, "password": PASSWORD}
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        return response.json().get("token")
    else:
        print("Failed to authenticate:", response.text)
        return None

@app.route('/')
def home():
    jwt_token = get_jwt_token()
    if jwt_token:
        return render_template('dashboard.html', jwt_token=jwt_token)
    else:
        return "Failed to authenticate with ThingsBoard", 401

# Fetch last 24 hours of telemetry data dynamically
@app.route('/realtime-telemetry/<device_id>')
def historical_telemetry(device_id,keys="temperature"):
    jwt_token = get_jwt_token()
    if not jwt_token:
        return jsonify({"error": "Authentication failed"}), 401

    end_ts = int(time.time() * 1000)
    start_ts = end_ts - (24 * 60 * 60 * 1000)
    keys = keys.split(",")
    
    data = get_historical_data(jwt_token, device_id, start_ts, end_ts, keys)
    return jsonify(data)

# Fetch telemetry data for a given device ID
def get_historical_data(jwt_token, device_id, start_ts, end_ts, keys):
    url = f"{THINGSBOARD_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
    params = {"keys": keys, "startTs": start_ts, "endTs": end_ts, "limit": 1000}
    headers = {"X-Authorization": f"Bearer {jwt_token}"}
    
    response = requests.get(url, headers=headers, params=params)
    return response.json() if response.status_code == 200 else {"error": "Failed to fetch telemetry data"}

# Fetch device telemetry data from the database
@app.route('/database-telemetry/<device_id>')
def fetch_telemetry(device_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """
        SELECT entity_id, key, ts, bool_v, str_v, long_v, dbl_v
        FROM ts_kv
        WHERE entity_id = %s
        ORDER BY ts DESC
        LIMIT 10;
    """
    cursor.execute(query, (device_id,))
    rows = cursor.fetchall()
    
    data = [
        {
            "entity_id": row[0],
            "key": row[1],
            "timestamp": row[2],
            "bool_value": row[3],
            "string_value": row[4],
            "long_value": row[5],
            "double_value": row[6],
        }
        for row in rows
    ]
    
    cursor.close()
    conn.close()
    return jsonify(data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7000, debug=True)

