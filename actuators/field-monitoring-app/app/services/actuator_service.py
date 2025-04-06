from sqlalchemy.orm import Session
from app.models.actuator import Actuator
from app.models.sensor import Sensor
from app.utils.thingsboard import get_jwt_token, get_device_token, send_telemetry,get_from_device,create_or_update_device_on_thingsboard,get_sensor_data
import time
import threading
from datetime import datetime

class ActuatorService:
    def __init__(self, db: Session):
        self.db = db
        self.monitoring_lock = threading.Lock()
        self.paused_actuators = {}  # Dictionary to track paused actuators
        

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
        
        # Add monitoring fields
        actuator_data["monitoring_active"] = True
        actuator_data["last_state_change"] = datetime.utcnow()
        actuator_data["last_monitoring_change"] = datetime.utcnow()

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
            
        # Track if state is changing
        if "state" in updated_data and updated_data["state"] != actuator.state:
            updated_data["last_state_change"] = datetime.utcnow()
            
        # Track if monitoring status is changing
        if "monitoring_active" in updated_data and updated_data["monitoring_active"] != actuator.monitoring_active:
            updated_data["last_monitoring_change"] = datetime.utcnow()
            
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

        
    def monitor_and_control(self, actuator_id: str, thresholds: dict, interval: int = 10):
        """
        Monitor sensor data and control the actuator in an endless loop.
        
        :param actuator_id: ID of the actuator to monitor and control.
        :param thresholds: Dictionary containing on/off thresholds for sensors.
        :param interval: Time interval (in seconds) between each monitoring cycle.
        """
        
        while True:
            # First check the database for monitoring state
            actuator = self.get_actuator(actuator_id)
            if not actuator:
                print(f"[ERROR] Actuator with ID {actuator_id} not found. Exiting monitoring loop.")
                break
                
            # Check both database and in-memory monitoring state
            with self.monitoring_lock:
                is_paused = self.paused_actuators.get(actuator_id, False)
                
            if is_paused or not actuator.monitoring_active:
                print(f"[INFO] Monitoring for actuator {actuator_id} is paused. Waiting for {interval} seconds.")
                time.sleep(interval)
                continue

            jwt_token = get_jwt_token()
            if not jwt_token:
                print("[ERROR] Failed to authenticate with ThingsBoard. Exiting monitoring loop.")
                break

            # Initialize a dictionary to store sensor values
            sensor_values = {}
            # Check the actuator's sensors
            print(f"[INFO] Monitoring actuator {actuator_id} with sensors: {[sensor.name for sensor in actuator.sensors]}")
            print(f"[INFO] Monitoring actuator {actuator_id} with sensor keys: {[sensor.keys for sensor in actuator.sensors]}")
            for sensor in actuator.sensors:
                print(f"[INFO] Monitoring sensor {sensor}")
                
                # Fetch telemetry data for each subscribed sensor
                end_ts = int(time.time() * 1000)
                start_ts = end_ts - (24 * 60 * 60 * 1000)
                limit = 1  # Fetch the latest data
                offset = 0  # No pagination
                try:
                    data = get_from_device(
                        jwt_token,
                        sensor.id,
                        start_ts=start_ts,
                        end_ts=end_ts,
                        keys=sensor.keys,
                        limit=limit,
                        offset=offset
                    )
                    print(f"[DEBUG] Data received for sensor {sensor.id}: {data}")
                    # Better data extraction logic - check if data exists and contains any keys
                    if data:
                        print(f"[INFO] Data received for sensor {sensor.id}.")
                        parsed_data = {}
                        for key in sensor.keys:
                            print(f"[DEBUG] Processing key: {key}")
                            if key in data and len(data[key]) > 0:
                                parsed_data[key] = float(data[key][-1]["value"])  # Convert the value to float
                                print(f"[DEBUG] Parsed value for {key}: {parsed_data[key]}")
                            else:
                                parsed_data[key] = 0.0  # Default value if no data found
                                print(f"[DEBUG] No data found for key {key}. Setting to None.")
                        
                        print(f"[DEBUG] Parsed data for sensor {sensor.name}: {parsed_data}")      
                        if all(value is not None for value in parsed_data.values()):
                            sensor_values[sensor.name] = parsed_data
                            print(f"[INFO] Successfully retrieved data for sensor {sensor.id}: {parsed_data}")
                        else:
                            print(f"[WARNING] Incomplete data for sensor {sensor.name}. Skipping this sensor.")
                    else:
                        print(f"[WARNING] No data received for sensor {sensor.id}.")
                        
                except Exception as e:
                    print(f"[ERROR] Exception occurred during data processing: {e}")
                        
            
            
            print(f"[INFO] Sensor values: {sensor_values}")
            # Use a model to determine the actuator state based on all sensor values and thresholds
            actuator_state = self.evaluate_model(sensor_values, thresholds, current_state=actuator.state)
            print(f"[INFO] Evaluated actuator state for {actuator_id}: {'ON' if actuator_state else 'OFF'}")

            # Only update state if it's changed
            if actuator.state != actuator_state:
                # Override the actuator state
                if self.override_actuator_state(actuator_id, actuator_state):
                    print(f"[INFO] Successfully updated actuator {actuator_id} state to {'ON' if actuator_state else 'OFF'}.")
                    # Update the last_state_change timestamp
                    actuator.last_state_change = datetime.utcnow()
                    self.db.commit()
                else:
                    print(f"[ERROR] Failed to update actuator {actuator_id} state.")

            # Wait for the specified interval before the next monitoring cycle
            print(f"[INFO] Waiting for {interval} seconds before the next monitoring cycle.")
            time.sleep(interval)
        
    def pause_actuator(self, actuator_id: str):
        """Pause monitoring for a specific actuator."""
        with self.monitoring_lock:
            self.paused_actuators[actuator_id] = True
            
        # Update the database with the monitoring state
        actuator = self.get_actuator(actuator_id)
        if actuator:
            actuator.monitoring_active = False
            actuator.last_monitoring_change = datetime.utcnow()
            self.db.commit()


    def resume_actuator(self, actuator_id: str):
        """Resume monitoring for a specific actuator."""
        with self.monitoring_lock:
            self.paused_actuators[actuator_id] = False
            
        # Update the database with the monitoring state
        actuator = self.get_actuator(actuator_id)
        if actuator:
            actuator.monitoring_active = True
            actuator.last_monitoring_change = datetime.utcnow()
            self.db.commit()

    def override_actuator_state(self, actuator_id: str, state: bool) -> bool:
        """Override the state of an actuator."""
        actuator = self.get_actuator(actuator_id)
        print(f"[DEBUG] Actuator found: {actuator}")
        if not actuator:
            return False
            
        # Only update if state is actually changing
        if actuator.state != state:
            actuator.state = state
            actuator.last_state_change = datetime.utcnow()
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
            
            
    def evaluate_model(self, sensor_values: dict, thresholds: dict, current_state=False) -> bool:
        """
        Evaluate the actuator state based on sensor values and thresholds.
        Returns True to turn the actuator ON, False to turn it OFF.
        """
        # Default to current state if no sensors found
        should_turn_on = current_state
        print(f"[DEBUG] Starting evaluation with current state: {should_turn_on}")
        
        # Iterate through all sensors with data
        for sensor_name, sensor_data in sensor_values.items():
            print(f"[DEBUG] Evaluating sensor {sensor_name} with value {sensor_data}")
            print(f"[DEBUG] Current state: {current_state}")
            print(f"[DEBUG] Thresholds: {thresholds}")
            
            # Process each key in the sensor data
            for key_name, value in sensor_data.items():
                # Look for thresholds by key name (not sensor name)
                on_threshold = thresholds.get("on_threshold", {}).get(key_name)
                off_threshold = thresholds.get("off_threshold", {}).get(key_name)
                
                # Check if we found thresholds for this key
                if on_threshold is None:
                    print(f"[WARNING] Missing on_threshold for key {key_name}. Skipping evaluation.")
                    continue
                    
                if off_threshold is None:
                    print(f"[WARNING] Missing off_threshold for key {key_name}. Using on_threshold.")
                    off_threshold = on_threshold  # Default to on_threshold
                    
                print(f"[DEBUG] Checking {key_name}: {value} against thresholds: ON={on_threshold}, OFF={off_threshold}")
                
                # Apply threshold logic
                if value >= on_threshold:
                    print(f"[INFO] {key_name} value {value} >= on_threshold {on_threshold} - turning ON")
                    should_turn_on = True
                elif value < off_threshold and should_turn_on:
                    print(f"[INFO] {key_name} value {value} < off_threshold {off_threshold} - turning OFF")
                    should_turn_on = False
        
        print(f"[DEBUG] Final decision: should_turn_on = {should_turn_on}")
        return should_turn_on
                

    
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
 