import json
import re
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_
from models.models import Farm, Field, Sensor, Actuator, Resource, init_db, get_session_factory
from utils.thingsboard import get_jwt_token, get_device_token, send_telemetry, create_or_update_device_on_thingsboard
import os

class FarmDataImporter:
    def __init__(self, db_path="farm_control.db"):
        # delete the database file if it exists
        if os.path.exists(db_path):
            os.remove(db_path)
        self.engine = init_db(db_path)
        self.SessionFactory = get_session_factory(self.engine)
    
    def import_from_json(self, json_file_path):
        with open(json_file_path, 'r') as f:
            data = json.load(f)
        
        farm_data = data.get('farm', {})
        
        with self.SessionFactory() as session:
            # Import farm
            farm = self._import_farm(session, farm_data)
            
            # Import fields
            self._import_fields(session, farm, farm_data.get('fields', []))
            
            # Import resources
            self._import_resources(session, farm, farm_data.get('resources', {}))
            
            # Create relationships between actuators and resources
            self._create_actuator_resource_relationships(session)
            
            # Create relationships between pumps and valves
            self._create_pump_valve_relationships(session)
            
            # Create field-resource relationships
            self._create_field_resource_relationships(session)
            
            session.commit()
            
        # After all components are created and relationships established,
        # register them with ThingsBoard
        self._register_components_with_thingsboard()
    
    def _import_farm(self, session: Session, farm_data):
        farm = Farm(
            id="F1",  # Assign a default ID
            name=farm_data.get('name', 'Unknown Farm'),
            address=farm_data.get('details', {}).get('address', ''),
            gps_lat=farm_data.get('details', {}).get('gps', {}).get('lat'),
            gps_long=farm_data.get('details', {}).get('gps', {}).get('long'),
            total_area=farm_data.get('details', {}).get('total_area', ''),
            created_at=datetime.now(),
            modified_at=datetime.now()
        )
        session.add(farm)
        return farm
    
    def _import_fields(self, session: Session, farm, fields_data):
        for field_entry in fields_data:
            for field_id, field_data in field_entry.items():
                # Create field
                field = Field(
                    id=field_id,
                    farm_id=farm.id,
                    name=field_data.get('name', ''),
                    crop=field_data.get('crop', ''),
                    area=field_data.get('area', ''),
                    boundary_gps=field_data.get('boundary_gps', {}),
                    created_at=datetime.now(),
                    modified_at=datetime.now()
                )
                session.add(field)
                session.flush()  # Ensure field has a valid ID
                
                # Import sensors for this field
                self._import_sensors(session, field, field_data.get('sensors', {}))
                
                # Import actuators for this field
                self._import_actuators(session, field, field_data.get('actuators', {}))
    
    def _import_sensors(self, session: Session, field, sensors_data):
        for sensor_type, sensors_list in sensors_data.items():
            for sensor_data in sensors_list:
                sensor_id = sensor_data.get('sensor_id') or sensor_data.get('camera_id')
                if not sensor_id:
                    continue
                
                sensor = Sensor(
                    id=sensor_id,
                    field_id=field.id,
                    type=sensor_type,
                    status=sensor_data.get('status', ''),
                    unit=sensor_data.get('unit', ''),
                    gps_lat=sensor_data.get('gps', {}).get('lat'),
                    gps_long=sensor_data.get('gps', {}).get('long'),
                    created_at=datetime.now(),
                    modified_at=datetime.now()
                )
                session.add(sensor)
    
    def _parse_to_dict(self, value_str):
        """Parse speed string into a dictionary with value and unit."""
        #print("Parsing value string:", value_str)
        if not value_str:
            return {"value": None, "unit": None}
        match = re.match(r"([\d.]+)\s*(\w+)", value_str)
        if match:
            return {"value": float(match.group(1)), "unit": match.group(2)}
        return {"value": None, "unit": None}

    def _import_actuators(self, session: Session, field, actuators_data):
        for actuator_type, actuators_list in actuators_data.items():
            for actuator_data in actuators_list:
                # Determine actuator ID based on type
                if actuator_type == 'pumps':
                    actuator_id = actuator_data.get('pump_id')
                elif actuator_type == 'water_valves' or actuator_type == 'fertilizer_dispensers':
                    actuator_id = actuator_data.get('valve_id')
                else:
                    actuator_id = None
                
                if not actuator_id:
                    continue
                base_speed=self._parse_to_dict(actuator_data.get('base_speed', '')),
                actuator = Actuator(
                    id=actuator_id,
                    field_id=field.id,
                    name=actuator_id,  # Using ID as name as per original code
                    type=actuator_type,
                    subtype=actuator_data.get('type', ''),
                    operation_type=actuator_data.get('operation_type', ''),
                    status=actuator_data.get('status', ''),
                    base_speed=base_speed,
                    created_at=datetime.now(),
                    modified_at=datetime.now()
                )
                session.add(actuator)
    
    def _import_resources(self, session: Session, farm, resources_data):
        if 'tanks' in resources_data:
            for tank_type, tank_data in resources_data['tanks'].items():
                capacity = self._parse_to_dict(tank_data.get('capacity', ''))
                current_level = self._parse_to_dict(tank_data.get('current_level', ''))
                resource = Resource(
                    id=tank_data.get('id', f'R-{tank_type}'),
                    farm_id=farm.id,  # Set the farm_id reference
                    name=tank_type,
                    capacity=capacity,  # Ensure capacity is a float
                    current_level=current_level,
                    content=tank_data.get('content', ''),
                    created_at=datetime.now(),
                    modified_at=datetime.now()
                )
                session.add(resource)
    
    def _create_actuator_resource_relationships(self, session: Session):
        # Map resources to actuator types
        resource_mappings = {
            'water_valves': 'water',
            'fertilizer_dispensers': ['fertilizer_slurry', 'liquid_fertilizer']
        }
        
        # Get all resources and actuators
        resources = {r.name: r for r in session.query(Resource).all()}
        actuators = session.query(Actuator).all()
        
        # Create relationships based on type
        for actuator in actuators:
            if actuator.type in resource_mappings:
                resource_names = resource_mappings[actuator.type]
                if isinstance(resource_names, str):
                    resource_names = [resource_names]
                
                for resource_name in resource_names:
                    if resource_name in resources:
                        actuator.resources.append(resources[resource_name])
                        # Update the modified_at timestamp
                        actuator.modified_at = datetime.now()
                        resources[resource_name].modified_at = datetime.now()
    
    def _create_pump_valve_relationships(self, session: Session):
        # Create relationships between pumps and their linked valves
        fields = session.query(Field).all()
        
        for field in fields:
            pumps = session.query(Actuator).filter(
                and_(Actuator.field_id == field.id, Actuator.type == 'pumps')
            ).all()
            
            valves = session.query(Actuator).filter(
                and_(
                    Actuator.field_id == field.id, 
                    Actuator.type.in_(['water_valves', 'fertilizer_dispensers'])
                )
            ).all()
            
            for pump in pumps:
                # Extract the numeric part from pump ID (e.g., "0100" from "PUMP-0100")
                pump_id_parts = pump.id.split('-')
                if len(pump_id_parts) < 2:
                    continue
                    
                pump_num = pump_id_parts[1]
                
                # Link valves that have the same numeric suffix
                for valve in valves:
                    valve_id_parts = valve.id.split('-')
                    if len(valve_id_parts) < 2:
                        continue
                        
                    valve_num = valve_id_parts[1]
                    
                    if valve_num == pump_num:
                        pump.linked_valves.append(valve)
                        # Update the modified_at timestamp
                        pump.modified_at = datetime.now()
                        valve.modified_at = datetime.now()

    def _create_field_resource_relationships(self, session: Session):
        """Create relationships between fields and resources based on actuator relationships."""
        # Get all actuators with their fields and resources
        actuators = session.query(Actuator).all()
        
        for actuator in actuators:
            if not actuator.field or not actuator.resources:
                continue
                
            # For each resource associated with this actuator,
            # ensure it's also associated with the field
            for resource in actuator.resources:
                if actuator.field not in resource.fields:
                    resource.fields.append(actuator.field)
                    resource.modified_at = datetime.now()
                    actuator.field.modified_at = datetime.now()

    def _register_components_with_thingsboard(self):
        """Register all components with ThingsBoard after import."""
        # Get JWT token for ThingsBoard authentication
        jwt_token = get_jwt_token()
        if not jwt_token:
            print("Failed to authenticate with ThingsBoard")
            return
        
        print("Registering components with ThingsBoard...")
        
        # Register sensors
        self._register_sensors_with_thingsboard(jwt_token)
        
        # Register actuators
        self._register_actuators_with_thingsboard(jwt_token)
        
        # Register resources
        self._register_resources_with_thingsboard(jwt_token)
        
        print("ThingsBoard registration complete.")
    
    def _register_sensors_with_thingsboard(self, jwt_token):
        """Register all sensors with ThingsBoard."""
        with self.SessionFactory() as session:
            sensors = session.query(Sensor).all()
            
            for sensor in sensors:
                # Get the associated field
                field = session.query(Field).filter(Field.id == sensor.field_id).first()
                if not field:
                    print(f"Warning: Sensor {sensor.id} not associated with any field. Skipping ThingsBoard registration.")
                    continue
                
                # Include minimal field information in device data
                device_data = {
                    "id": sensor.id,
                    "name": f"Sensor-{sensor.id}",
                    "type": sensor.type,
                    "label": f"{field.name} - {sensor.type.replace('_', ' ').title()}",
                    "additionalInfo": {
                        "field_id": field.id,
                        "field_name": field.name
                    }
                }
                
                # Create or update the sensor in ThingsBoard
                original_id = sensor.id  # Store the original ID
                tb_device_id = create_or_update_device_on_thingsboard(jwt_token, device_data, "sensor")
                
                if tb_device_id and tb_device_id != original_id:
                    # Update the sensor with the ThingsBoard ID
                    sensor.thingsboard_id = tb_device_id
                    sensor.modified_at = datetime.now()
                    session.commit()
                    
                    # Get the device token for telemetry
                    device_token = get_device_token(jwt_token, tb_device_id)
                    
                    if device_token:
                        # Send basic telemetry data
                        telemetry = {
                            "status": sensor.status,
                            "field_id": field.id
                        }
                        send_telemetry(device_token, telemetry)
                        print(f"Sent telemetry for sensor {original_id} (ThingsBoard ID: {tb_device_id})")
                    
    def _register_actuators_with_thingsboard(self, jwt_token):
        """Register all actuators with ThingsBoard."""
        with self.SessionFactory() as session:
            # Load actuators with their field relationships
            actuators = session.query(Actuator).all()
            
            for actuator in actuators:
                # Get the associated field
                field = session.query(Field).filter(Field.id == actuator.field_id).first()
                if not field:
                    print(f"Warning: Actuator {actuator.id} not associated with any field. Skipping ThingsBoard registration.")
                    continue
                
                # Include minimal field information in device data
                device_data = {
                    "id": actuator.id,
                    "name": f"Actuator-{actuator.id}",
                    "type": actuator.type,
                    "label": f"{field.name} - {actuator.type.replace('_', ' ').title()}",
                    "additionalInfo": {
                        "field_id": field.id,
                        "field_name": field.name,
                        "subtype": actuator.subtype,
                        "operation_type": actuator.operation_type
                    }
                }
                
                # Create or update the actuator in ThingsBoard
                original_id = actuator.id
                tb_device_id = create_or_update_device_on_thingsboard(jwt_token, device_data, "actuator")
                
                if tb_device_id and tb_device_id != original_id:
                    # Update the actuator with the ThingsBoard ID
                    actuator.thingsboard_id = tb_device_id
                    actuator.modified_at = datetime.now()
                    session.commit()
                    
                    # Get the device token for telemetry
                    device_token = get_device_token(jwt_token, tb_device_id)
                    
                    if device_token:
                        # Send basic telemetry data
                        telemetry = {
                            "status": actuator.status,
                            "field_id": field.id,
                            "base_speed": actuator.base_speed
                        }
                        send_telemetry(device_token, telemetry)
                        print(f"Sent telemetry for actuator {original_id} (ThingsBoard ID: {tb_device_id})")
    
    def _register_resources_with_thingsboard(self, jwt_token):
        """Register all resources with ThingsBoard."""
        with self.SessionFactory() as session:
            resources = session.query(Resource).all()
            
            for resource in resources:
                # Extract numeric values from capacity and current_level
                try:
                    capacity =resource.capacity.get('value', 0.0) or 0.0  # Ensure capacity is a float
                    current_level = resource.current_level.get('value', 0.0) or 0.0  # Ensure current_level is a float
                except ValueError:
                    print(f"Skipping resource {resource.id} due to invalid numeric values.")
                    continue
                
                # Enrich device data with associated fields
                associated_fields = []
                for field in resource.fields:
                    associated_fields.append({
                        "id": field.id,
                        "name": field.name
                    })
                
                # Create device data for this resource
                device_data = {
                    "id": resource.id,
                    "name": f"Resource-{resource.id}",
                    "type": "resource",
                    "label": f"{resource.name.replace('_', ' ').title()} Tank",
                    "additionalInfo": {
                        "content": resource.content,
                        "associated_fields": associated_fields
                    }
                }
                
                # Create or update the resource in ThingsBoard
                original_id = resource.id
                tb_device_id = create_or_update_device_on_thingsboard(jwt_token, device_data, "resource")
                
                if tb_device_id and tb_device_id != original_id:
                    # Update the resource with the ThingsBoard ID
                    resource.thingsboard_id = tb_device_id
                    resource.modified_at = datetime.now()
                    session.commit()
                    
                    # Get the device token for telemetry
                    device_token = get_device_token(jwt_token, tb_device_id)
                    
                    if device_token:
                       
                        # Send basic telemetry data
                        capacity_value = capacity
                        current_level_value = current_level
                        telemetry = {
                            "current_level": current_level_value,
                            "capacity": capacity_value,
                            "percentage_full": current_level_value / capacity_value * 100 if capacity_value > 0 else 0
                        }
                        send_telemetry(device_token, telemetry)
                        print(f"Sent telemetry for resource {original_id} (ThingsBoard ID: {tb_device_id})")

if __name__ == "__main__":
    importer = FarmDataImporter()
    importer.import_from_json("farm_model.json")
    print("Farm data imported successfully")