from flask import Flask, render_template, request, jsonify
import requests
import time
import psycopg2
from flask_cors import CORS
import os

app = Flask(__name__)
host = os.getenv('THINGSBOARD_HOST', 'localhost')

# Use Flask-CORS properly - don't try to mix with FastAPI middleware
CORS(app, resources={
    r"/*": {
        "origins": ["http://3.89.163.209:8000", "http://3.89.163.209:8080", 
                    "http://localhost:8080", "http://localhost:8000"],
        "supports_credentials": True
    }
})

# ThingsBoard settings
THINGSBOARD_URL = f"http://{host}:8080" if host == 'localhost' else f"http://{host}:9090"
USERNAME = "tenant@thingsboard.org"
PASSWORD = "tenant"
DB_HOST = os.getenv('DB_HOST', 'postgres')  # Use 'postgres' as the host for the PostgreSQL container
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'thingsboard')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

# Global variable to store the JWT token
jwt_token = None

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
    global jwt_token
    if jwt_token:
        return jwt_token

    url = f"{THINGSBOARD_URL}/api/auth/login"
    payload = {"username": USERNAME, "password": PASSWORD}
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        print("Authenticated successfully")
        jwt_token = response.json().get("token")
        return jwt_token
    else:
        print("Failed to authenticate:", response.text)
        return None

@app.route('/')
def home():
    jwt_token = get_jwt_token()
    if jwt_token:
        # # Set host dynamically based on environment
        # if os.getenv('FLASK_ENV') == 'development':
        #     host = 'localhost'  # Local development
        # else:
        #     host = '3.89.163.209'  # Public IP address or domain

        # # Construct the full URL to ThingsBoard dashboard
        # dashboard_url = f"http://{host}:8080/dashboards/home?token={jwt_token}"
        
        # Return the dashboard page
        return render_template('dashboard.html', jwt_token=jwt_token)
    else:
        return "Failed to authenticate with ThingsBoard", 401

# Fetch last 24 hours of telemetry data dynamically with pagination
@app.route('/realtime-telemetry/<device_id>')
def historical_telemetry(device_id, keys="temperature"):
    jwt_token = get_jwt_token()
    if not jwt_token:
        return jsonify({"error": "Authentication failed"}), 401

    end_ts = int(time.time() * 1000)
    start_ts = end_ts - (24 * 60 * 60 * 1000)
    keys = keys.split(",")
    
    # Get pagination parameters from request
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 100, type=int)
    offset = (page - 1) * page_size
    
    data = get_historical_data(jwt_token, device_id, start_ts, end_ts, keys, page_size, offset)
    return jsonify(data)

# Fetch telemetry data for a given device ID with pagination
def get_historical_data(jwt_token, device_id, start_ts, end_ts, keys, limit, offset):
    url = f"{THINGSBOARD_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
    params = {
        "keys": keys,
        "startTs": start_ts,
        "endTs": end_ts,
        "limit": limit,
        "offset": offset
    }
    headers = {"X-Authorization": f"Bearer {jwt_token}"}
    
    response = requests.get(url, headers=headers, params=params)
    return response.json() if response.status_code == 200 else {"error": "Failed to fetch telemetry data"}

# Fetch device telemetry data from the database with pagination
@app.route('/database-telemetry/<device_id>')
def fetch_telemetry(device_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get pagination parameters from request
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 100, type=int)
    offset = (page - 1) * page_size
    
    query = """
        SELECT entity_id, key, ts, bool_v, str_v, long_v, dbl_v
        FROM ts_kv
        WHERE entity_id = %s
        ORDER BY ts DESC
        LIMIT %s OFFSET %s;
    """
    cursor.execute(query, (device_id, page_size, offset))
    rows = cursor.fetchall()
    
    data = []
    for row in rows:
        value = None
        if row[3] is not None:  # bool_v
            value = row[3]
        elif row[4] is not None:  # str_v
            value = row[4]
        elif row[5] is not None:  # long_v
            value = row[5]
        elif row[6] is not None:  # dbl_v
            value = row[6]
        
        data.append({
            "ts": row[2],  # timestamp
            "value": value
        })
    
    cursor.close()
    conn.close()
    return jsonify(data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7000, debug=True)