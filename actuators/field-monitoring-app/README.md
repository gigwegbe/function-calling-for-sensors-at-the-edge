# Field Monitoring Application

This project is a field monitoring application that allows for the management of multiple sensors and actuator devices. It provides an API for subscribing to different sensors, listening to their conditions, and overriding actuator states based on admin modifications.

## Features

- **Device Management**: Create, update, and retrieve information about actuator and sensor devices.
- **Sensor Subscription**: Devices can subscribe to various sensors to monitor their conditions.
- **Actuator Control**: Override actuator states based on sensor data and admin inputs.
- **RESTful API**: Interact with the application using a well-defined API.

## Project Structure

```
field-monitoring-app
├── app
│   ├── __init__.py
│   ├── main.py
│   ├── models
│   │   ├── __init__.py
│   │   └── device.py
│   ├── routes
│   │   ├── __init__.py
│   │   ├── devices.py
│   │   └── sensors.py
│   ├── services
│   │   ├── __init__.py
│   │   ├── actuator_service.py
│   │   └── sensor_service.py
│   └── utils
│       ├── __init__.py
│       └── db.py
├── requirements.txt
├── README.md
└── .gitignore
```

## Setup Instructions

### Option 1: Run Locally

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd field-monitoring-app
   ```

2. **Create a virtual environment** (optional but recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application**:
   ```bash
   python app/main.py
   ```

Alternatively, you can run the application using the following command:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8090 --reload
```

### Option 2: Run with Docker

1. **Build the Docker image**:
   ```bash
   docker build -t field-monitoring-app .
   ```

2. **Run the Docker container**:
   ```bash
   docker run -p 8090:8090 field-monitoring-app
   ```

3. The application will be available at `http://localhost:8090`.

### Option 3: Use Docker Compose

1. **Run the application with Docker Compose**:
   ```bash
   docker-compose up -d --build
   ```

2. The application will be available at `http://localhost:8090` in docker envernoment but `http://localhost:8100` out of docker env

---

## API Endpoints

### **Actuator Endpoints**

- **Create an Actuator**:  
  `POST /actuators/`  
  Example Body:
  ```json
  {
      "name": "Irrigation Pump",
      "type": "pump",
      "label": "Field Pump",
      "state": false,
      "additionalInfo": {"description": "Controls irrigation"}
  }
  ```

- **Retrieve an Actuator by ID**:  
  `GET /actuators/{actuator_id}`

- **Retrieve All Actuators**:  
  `GET /actuators/`

- **Update an Actuator**:  
  `PUT /actuators/{actuator_id}`  
  Example Body:
  ```json
  {
      "name": "Updated Pump",
      "type": "pump",
      "label": "Updated Field Pump",
      "state": true,
      "additionalInfo": {"description": "Updated description"}
  }
  ```

- **Delete an Actuator**:  
  `DELETE /actuators/{actuator_id}`

- **Subscribe an Actuator to a Sensor**:  
  `POST /actuators/{actuator_id}/subscribe/{sensor_id}`

- **Unsubscribe an Actuator from a Sensor**:  
  `DELETE /actuators/{actuator_id}/unsubscribe/{sensor_id}`

- **Monitor and Control Actuator**:  
  `POST /actuators/{actuator_id}/monitor`  
  Example Body:
  ```json
  {
      "on_threshold": {
          "temperature_sensor": 30.0,
          "humidity_sensor": 50.0
      },
      "off_threshold": {
          "temperature_sensor": 20.0,
          "humidity_sensor": 30.0
      }
  }
  ```

- **Override Actuator State**:  
  `POST /actuators/{actuator_id}/override`  
  Example Body:
  ```json
  {
      "state": true
  }
  ```

### **Sensor Endpoints**

- **Create a Sensor**:  
  `POST /sensors/`  
  Example Body:
  ```json
  {
      "name": "Soil Moisture Sensor",
      "type": "soil_moisture",
      "unit": "%",
      "threshold": 30.0,
      "label": "Field Sensor",
      "additionalInfo": {"description": "Measures soil moisture levels"}
  }
  ```

- **Retrieve a Sensor by ID**:  
  `GET /sensors/{sensor_id}`

- **Retrieve All Sensors**:  
  `GET /sensors/`

- **Update a Sensor**:  
  `PUT /sensors/{sensor_id}`  
  Example Body:
  ```json
  {
      "name": "Updated Soil Moisture Sensor",
      "type": "soil_moisture",
      "unit": "%",
      "threshold": 25.0,
      "label": "Updated Field Sensor",
      "additionalInfo": {"description": "Updated description"}
  }
  ```

- **Delete a Sensor**:  
  `DELETE /sensors/{sensor_id}`

- **Retrieve a Sensor by Name**:  
  `GET /sensors/name/{name}`

- **Retrieve Sensors by State**:  
  `GET /sensors/state/{state}`

---

## License

This project is licensed under the MIT License. See the LICENSE file for more details.