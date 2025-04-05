from sqlalchemy.orm import Session
from app.models.sensor import Sensor
from app.utils.thingsboard import get_jwt_token, create_or_update_device_on_thingsboard

class SensorService:
    def __init__(self, db: Session):
        self.db = db

    def get_sensor(self, sensor_id: str) -> Sensor:
        """Retrieve a sensor by its ID."""
        return self.db.query(Sensor).filter(Sensor.id == sensor_id).first()

    def create_sensor(self, sensor_data: dict) -> Sensor:
        """Create a new sensor both locally and on ThingsBoard."""
        # Authenticate with ThingsBoard
        jwt_token = get_jwt_token()
        if not jwt_token:
            raise Exception("Failed to authenticate with ThingsBoard")
        
        # Create the sensor on ThingsBoard
        thingsboard_device_id = create_or_update_device_on_thingsboard(jwt_token, sensor_data, device_type="sensor")
        if not thingsboard_device_id:
            raise Exception("Failed to create sensor on ThingsBoard")
    
        # Add the ThingsBoard device ID to the local sensor data
        sensor_data["id"] = thingsboard_device_id
    
        # Create the sensor locally
        sensor = Sensor(**sensor_data)
        self.db.add(sensor)
        self.db.commit()
        self.db.refresh(sensor)
        return sensor

    def update_sensor(self, sensor_id: str, updated_data: dict) -> Sensor:
        """Update an existing sensor."""
        sensor = self.get_sensor(sensor_id)
        if not sensor:
            return None
        for key, value in updated_data.items():
            setattr(sensor, key, value)
        self.db.commit()
        self.db.refresh(sensor)
        return sensor

    def delete_sensor(self, sensor_id: str) -> bool:
        """Delete a sensor."""
        sensor = self.get_sensor(sensor_id)
        if not sensor:
            return False
        self.db.delete(sensor)
        self.db.commit()
        return True
    
    def get_all_sensors(self) -> list:
        """Retrieve all sensors."""
        return self.db.query(Sensor).all()
    
    def get_sensor_by_name(self, name: str) -> Sensor:
        """Retrieve a sensor by its name."""
        return self.db.query(Sensor).filter(Sensor.name == name).first()
    
    def get_sensor_by_type(self, sensor_type: str) -> list:
        """Retrieve sensors by their type."""
        return self.db.query(Sensor).filter(Sensor.type == sensor_type).all()
   
    