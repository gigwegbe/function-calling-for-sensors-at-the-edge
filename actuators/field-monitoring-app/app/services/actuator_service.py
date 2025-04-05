from sqlalchemy.orm import Session
from app.models.actuator import Actuator
from app.models.sensor import Sensor
from app.utils.thingsboard import get_jwt_token, get_device_token, send_telemetry,get_from_device,create_or_update_device_on_thingsboard,get_sensor_data
import time

class ActuatorService:
    def __init__(self, db: Session):
        self.db = db

    def get_actuator(self, actuator_id: str) -> Actuator:
        """Retrieve an actuator by its ID."""
        return self.db.query(Actuator).filter(Actuator.id == actuator_id).first()

    def create_actuator(self, actuator_data: dict) -> Actuator:
        """Create a new actuator both locally and on ThingsBoard."""
        
        
        """Example actuator_data:
        {
        "name": "Test pump",
        "type": "pump",
        "label": "Field Irrigation Pump",
        "additionalInfo": {"description": "Pump actuator for field irrigation system"}
        }
        """
        # Create the actuator on ThingsBoard
        jwt_token = get_jwt_token()
        if not jwt_token:
            raise Exception("Failed to authenticate with ThingsBoard")
        
        # Use the ThingsBoard utility to create the device
        thingsboard_device_id = create_or_update_device_on_thingsboard(jwt_token, actuator_data)
        if not thingsboard_device_id:
            raise Exception("Failed to create actuator on ThingsBoard")

        # Add the ThingsBoard device ID to the local actuator data
        actuator_data["id"] = thingsboard_device_id

        # Create the actuator locally
        actuator = Actuator(**actuator_data)
        self.db.add(actuator)
        self.db.commit()
        self.db.refresh(actuator)
        return actuator
    def update_actuator(self, actuator_id: str, updated_data: dict) -> Actuator:
        """Update an existing actuator."""
        actuator = self.get_actuator(actuator_id)
        if not actuator:
            return None
        for key, value in updated_data.items():
            setattr(actuator, key, value)
        self.db.commit()
        self.db.refresh(actuator)
        return actuator
    def delete_actuator(self, actuator_id: str) -> bool:
        """Delete an actuator."""
        actuator = self.get_actuator(actuator_id)
        if not actuator:
            return False
        self.db.delete(actuator)
        self.db.commit()
        return True
    
    def get_all_actuators(self) -> list:
        """Retrieve all actuators."""
        return self.db.query(Actuator).all()
    
    def get_actuator_by_name(self, name: str) -> Actuator:
        """Retrieve an actuator by its name."""
        return self.db.query(Actuator).filter(Actuator.name == name).first()
    
    def get_actuator_by_type(self, actuator_type: str) -> list:
        """Retrieve actuators by their type."""
        return self.db.query(Actuator).filter(Actuator.type == actuator_type).all()
    
    def subscribe_to_sensor(self, actuator_id: str, sensor_id: str) -> bool:
        """Subscribe an actuator to a sensor."""
        actuator = self.get_actuator(actuator_id)
        sensor = self.db.query(Sensor).filter(Sensor.id == sensor_id).first()
        if not actuator or not sensor:
            return False
        if sensor not in actuator.sensors:
            actuator.sensors.append(sensor)
        self.db.commit()
        return True
    
    def get_subscribed_sensors(self, actuator_id: str) -> list:
        """Retrieve all sensors subscribed to an actuator."""
        actuator = self.get_actuator(actuator_id)
        if not actuator:
            return []
        return actuator.sensors
    
    def unsubscribe_from_sensor(self, actuator_id: str, sensor_id: str) -> bool:
        """Unsubscribe an actuator from a sensor."""
        actuator = self.get_actuator(actuator_id)
        sensor = self.db.query(Sensor).filter(Sensor.id == sensor_id).first()
        if not actuator or not sensor:
            return False
        if sensor in actuator.sensors:
            actuator.sensors.remove(sensor)
        self.db.commit()
        return True

    def monitor_and_control(self, actuator_id: str, thresholds: dict):
        """Monitor sensor data and control the actuator."""
        actuator = self.get_actuator(actuator_id)
        if not actuator:
            return False
    
        jwt_token = get_jwt_token()
        if not jwt_token:
            return False
    
        # Initialize a dictionary to store sensor values
        sensor_values = {}
    
        for sensor in actuator.sensors:
            # Fetch telemetry data for each subscribed sensor
            data = get_from_device(
                jwt_token,
                sensor.id,
                start_ts=0,
                end_ts=int(time.time() * 1000),
                keys=["value"],
                limit=1,
                offset=0
            )
            if not data:
                continue
    
            # Extract the latest sensor value
            sensor_value = data.get("value", [{}])[0].get("value", 0)
            sensor_values[sensor.name] = sensor_value
    
        # Use a model to determine the actuator state based on all sensor values and thresholds
        actuator_state = self.evaluate_model(sensor_values, thresholds)
    
        # Override the actuator state
        self.override_actuator_state(actuator_id, actuator_state)
    
        return True
    
    
    def evaluate_model(self, sensor_values: dict, thresholds: dict) -> bool:
        """
        Evaluate the actuator state based on sensor values and thresholds.
        Returns True to turn the actuator ON, False to turn it OFF.
        """
        # Check if all sensors meet the "on_threshold" condition
        for sensor_name, sensor_value in sensor_values.items():
            on_threshold = thresholds.get("on_threshold", {}).get(sensor_name, float("inf"))
            if sensor_value <= on_threshold:
                break
        else:
            # All sensors meet the "on_threshold" condition
            return True
    
        # Check if any sensor meets the "off_threshold" condition
        for sensor_name, sensor_value in sensor_values.items():
            off_threshold = thresholds.get("off_threshold", {}).get(sensor_name, float("-inf"))
            if sensor_value < off_threshold:
                return False
    
        # Default: Keep the actuator OFF
        return False
    
    def override_actuator_state(self, actuator_id: str, state: bool) -> bool:
        """Override the state of an actuator."""
        actuator = self.get_actuator(actuator_id)
        if not actuator:
            return False
        actuator.state = state
        self.db.commit()

        # Send telemetry to ThingsBoard
        jwt_token = get_jwt_token()
        if not jwt_token:
            return False
        device_token = get_device_token(jwt_token, actuator_id)
        if not device_token:
            return False
        telemetry_data = {"state": state}
        return send_telemetry(device_token, telemetry_data)
    
    def get_actuators_by_state(self, state: bool) -> list:
        """Retrieve actuators by their state."""
        return self.db.query(Actuator).filter(Actuator.state == state).all()
    
    def get_sensor_data(self, actuator_id: str, keys: list):
        """Retrieve the latest telemetry data for a given actuator."""
        actuator = self.get_actuator(actuator_id)
        if not actuator:
            return None
        jwt_token = get_jwt_token()
        if not jwt_token:
            return None
        device_id = actuator.id
        
        return get_sensor_data(jwt_token, device_id, keys)
    
    def get_sensor_data_by_id(self, actuator_id: str, sensor_id: str):
        """Retrieve the latest telemetry data for a given sensor."""
        actuator = self.get_actuator(actuator_id)
        if not actuator:
            return None
        sensor = self.db.query(Sensor).filter(Sensor.id == sensor_id).first()
        if not sensor:
            return None
        jwt_token = get_jwt_token()
        if not jwt_token:
            return None
        device_id = actuator.id
        
        return get_sensor_data(jwt_token, device_id, keys=[sensor_id])
    
    def get_actuators_by_type(self, actuator_type: str) -> list:
        """Retrieve actuators by their type."""
        return self.db.query(Actuator).filter(Actuator.type == actuator_type).all()
 