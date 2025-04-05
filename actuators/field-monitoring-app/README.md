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

## Usage

### API Endpoints

- **Devices**
  - `POST /devices`: Create a new device.
  - `GET /devices`: Retrieve all devices.
  - `PUT /devices/{id}`: Update a device by ID.
  
- **Sensors**
  - `POST /sensors`: Create a new sensor.
  - `GET /sensors`: Retrieve all sensors.
  - `PUT /sensors/{id}`: Update a sensor by ID.

## API Documentation

Refer to the API documentation for detailed information on request and response formats, as well as examples for each endpoint.

## Contributing

Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.