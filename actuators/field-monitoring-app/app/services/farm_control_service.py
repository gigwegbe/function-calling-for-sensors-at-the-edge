from models.models import Farm, Field, Sensor, Actuator, Resource, get_session_factory
from utils.thingsboard import get_jwt_token, get_device_token, send_telemetry, create_or_update_device_on_thingsboard
from sqlalchemy.orm import joinedload

class FarmControlService:
    def __init__(self, session_factory):
        self.session_factory = session_factory
    
    def get_all_farms(self, include_related=True):
        """Get all farms with optional related entities (fields, sensors, actuators, resources)"""
        with self.session_factory() as session:
            # Build query with appropriate joins for eager loading
            query = session.query(Farm)
            
            if include_related:
                # Explicitly join all relationships for complete eager loading
                query = query.options(
                    joinedload(Farm.fields).joinedload(Field.sensors),
                    joinedload(Farm.fields).joinedload(Field.actuators),
                    joinedload(Farm.fields).joinedload(Field.resources)
                )
            
            farms = query.all()
            return [farm.to_dict(include_related=include_related) for farm in farms]
    
    def get_farm_by_id(self, farm_id, include_related=True):
        """Get a specific farm with optional related entities"""
        with self.session_factory() as session:
            query = session.query(Farm).filter(Farm.id == farm_id)
            
            if include_related:
                query = query.options(
                    joinedload(Farm.fields).joinedload(Field.sensors),
                    joinedload(Farm.fields).joinedload(Field.actuators),
                    joinedload(Farm.fields).joinedload(Field.resources)
                )
            
            farm = query.first()
            return farm.to_dict(include_related=include_related) if farm else None
    
    def get_all_fields(self, include_related=True):
        """Get all fields with optional related entities (sensors, actuators)"""
        with self.session_factory() as session:
            query = session.query(Field)
            
            if include_related:
                query = query.options(
                    joinedload(Field.sensors),
                    joinedload(Field.actuators),
                    joinedload(Field.resources)
                )
            
            fields = query.all()
            return [field.to_dict(include_related=include_related) for field in fields]
    
    def get_field_by_id(self, field_id, include_related=True):
        """Get a specific field with optional related entities"""
        with self.session_factory() as session:
            query = session.query(Field).filter(Field.id == field_id)
            
            if include_related:
                query = query.options(
                    joinedload(Field.sensors),
                    joinedload(Field.actuators),
                    joinedload(Field.resources)
                )
            
            field = query.first()
            return field.to_dict(include_related=include_related) if field else None
    
    def get_field_by_name(self, field_name, include_related=True):
        """Get a specific field by name with optional related entities"""
        with self.session_factory() as session:
            query = session.query(Field).filter(Field.name == field_name)
            
            if include_related:
                query = query.options(
                    joinedload(Field.sensors),
                    joinedload(Field.actuators),
                    joinedload(Field.resources)
                )
            
            field = query.first()
            return field.to_dict(include_related=include_related) if field else None
    
    def get_all_sensors(self, include_related=True):
        """Get all sensors with optional related field"""
        with self.session_factory() as session:
            query = session.query(Sensor)
            
            if include_related:
                query = query.options(joinedload(Sensor.field))
            
            sensors = query.all()
            return [sensor.to_dict(include_related=include_related) for sensor in sensors]
    
    def get_sensor_by_id(self, sensor_id, include_related=True):
        """Get a specific sensor with optional related field"""
        with self.session_factory() as session:
            query = session.query(Sensor).filter(Sensor.id == sensor_id)
            
            if include_related:
                query = query.options(joinedload(Sensor.field))
            
            sensor = query.first()
            return sensor.to_dict(include_related=include_related) if sensor else None
    
    def get_all_actuators(self, include_related=True):
        """Get all actuators with optional related entities"""
        with self.session_factory() as session:
            query = session.query(Actuator)
            
            if include_related:
                query = query.options(
                    joinedload(Actuator.resources),
                    joinedload(Actuator.linked_valves),
                    joinedload(Actuator.linked_pumps)
                )
            
            actuators = query.all()
            return [actuator.to_dict(include_related=include_related) for actuator in actuators]
    
    def get_actuator_by_type(self, actuator_type, include_related=True):
        """Get actuators by type with optional related entities"""
        with self.session_factory() as session:
            query = session.query(Actuator).filter(Actuator.type == actuator_type)
            
            if include_related:
                query = query.options(
                    joinedload(Actuator.resources),
                    joinedload(Actuator.linked_valves),
                    joinedload(Actuator.linked_pumps)
                )
            
            actuators = query.all()
            return [actuator.to_dict(include_related=include_related) for actuator in actuators]
    
    def get_actuator_by_id(self, actuator_id, include_related=True):
        """Get a specific actuator with optional related entities"""
        with self.session_factory() as session:
            query = session.query(Actuator).filter(Actuator.id == actuator_id)
            
            if include_related:
                query = query.options(
                    joinedload(Actuator.resources),
                    joinedload(Actuator.linked_valves),
                    joinedload(Actuator.linked_pumps)
                )
            
            actuator = query.first()
            return actuator.to_dict(include_related=include_related) if actuator else None
    
    def get_all_resources(self, include_related=True):
        """Get all resources with optional related entities"""
        with self.session_factory() as session:
            query = session.query(Resource)
            
            if include_related:
                query = query.options(
                    joinedload(Resource.fields),
                    joinedload(Resource.actuators)
                )
            
            resources = query.all()
            return [resource.to_dict(include_related=include_related) for resource in resources]
    
    def get_resource_by_id(self, resource_id, include_related=True):
        """Get a specific resource with optional related entities"""
        with self.session_factory() as session:
            query = session.query(Resource).filter(Resource.id == resource_id)
            
            if include_related:
                query = query.options(
                    joinedload(Resource.fields),
                    joinedload(Resource.actuators)
                )
            
            resource = query.first()
            return resource.to_dict(include_related=include_related) if resource else None
    
    # Updated association methods
    def update_sensor_field(self, sensor_id, field_id):
        """Update a sensor's associated field"""
        with self.session_factory() as session:
            sensor = session.query(Sensor).filter(Sensor.id == sensor_id).first()
            field = session.query(Field).filter(Field.id == field_id).first()
            
            if not sensor or not field:
                return {"error": "Sensor or field not found"}
            
            # Update the field_id directly
            sensor.field_id = field_id
            session.commit()
                
            return {"status": "success", "message": f"Sensor {sensor_id} updated to field {field_id}"}
    
    def associate_actuator_with_field(self, actuator_id, field_id):
        """Associate an actuator with a field"""
        with self.session_factory() as session:
            actuator = session.query(Actuator).filter(Actuator.id == actuator_id).first()
            field = session.query(Field).filter(Field.id == field_id).first()
            
            if not actuator or not field:
                return {"error": "Actuator or field not found"}
            
            if field not in actuator.fields:
                actuator.fields.append(field)
                session.commit()
                
            return {"status": "success", "message": f"Actuator {actuator_id} associated with field {field_id}"}
    
    def associate_resource_with_field(self, resource_id, field_id):
        """Associate a resource with a field"""
        with self.session_factory() as session:
            resource = session.query(Resource).filter(Resource.id == resource_id).first()
            field = session.query(Field).filter(Field.id == field_id).first()
            
            if not resource or not field:
                return {"error": "Resource or field not found"}
            
            if field not in resource.fields:
                resource.fields.append(field)
                session.commit()
                
            return {"status": "success", "message": f"Resource {resource_id} associated with field {field_id}"}
    
    def associate_actuator_with_resource(self, actuator_id, resource_id):
        """Associate an actuator with a resource"""
        with self.session_factory() as session:
            actuator = session.query(Actuator).filter(Actuator.id == actuator_id).first()
            resource = session.query(Resource).filter(Resource.id == resource_id).first()
            
            if not actuator or not resource:
                return {"error": "Actuator or resource not found"}
            
            if resource not in actuator.resources:
                actuator.resources.append(resource)
                session.commit()
                
            return {"status": "success", "message": f"Actuator {actuator_id} associated with resource {resource_id}"}
    
    def associate_pump_with_valve(self, pump_id, valve_id):
        """Associate a pump with a valve"""
        with self.session_factory() as session:
            pump = session.query(Actuator).filter(Actuator.id == pump_id).first()
            valve = session.query(Actuator).filter(Actuator.id == valve_id).first()
            
            if not pump or not valve:
                return {"error": "Pump or valve not found"}
            
            if valve.type not in ['water_valves', 'fertilizer_dispensers']:
                return {"error": f"Actuator {valve_id} is not a valve type"}
                
            if pump.type != 'pump':
                return {"error": f"Actuator {pump_id} is not a pump type"}
            
            if valve not in pump.linked_valves:
                pump.linked_valves.append(valve)
                session.commit()
                
            return {"status": "success", "message": f"Pump {pump_id} associated with valve {valve_id}"}
    
    # Control functions
    def get_actuators_by_field(self, field_id, include_related=True):
        """Get all actuators for a specific field"""
        with self.session_factory() as session:
            field = session.query(Field).filter(Field.id == field_id).options(
                joinedload(Field.actuators)
            ).first()
            
            if not field:
                return []
            
            return [actuator.to_dict(include_related=include_related) for actuator in field.actuators]
    
    def get_actuators_by_field_name(self, field_name, include_related=True):
        """Get all actuators for a field by name"""
        with self.session_factory() as session:
            field = session.query(Field).filter(Field.name == field_name).options(
                joinedload(Field.actuators)
            ).first()
            
            if not field:
                return []
            
            return [actuator.to_dict(include_related=include_related) for actuator in field.actuators]
    
    # Updated method to use direct relationship
    def get_sensors_by_field(self, field_id, include_related=True):
        """Get all sensors for a specific field"""
        with self.session_factory() as session:
            sensors = session.query(Sensor).filter(Sensor.field_id == field_id).all()
            
            if not sensors:
                return []
            
            return [sensor.to_dict(include_related=include_related) for sensor in sensors]
    
    def get_active_actuators(self, include_related=True):
        """Get all actuators with 'open' status"""
        with self.session_factory() as session:
            query = session.query(Actuator).filter(Actuator.status == 'open')
            
            if include_related:
                query = query.options(
                    joinedload(Actuator.resources)
                )
            
            active_actuators = query.all()
            return [actuator.to_dict(include_related=include_related) for actuator in active_actuators]
        
    def get_inactive_actuators(self, include_related=True):
        """Get all actuators with 'close' status"""
        with self.session_factory() as session:
            query = session.query(Actuator).filter(Actuator.status == 'close')
            
            if include_related:
                query = query.options(
                    joinedload(Actuator.resources)
                )
            
            inactive_actuators = query.all()
            return [actuator.to_dict(include_related=include_related) for actuator in inactive_actuators]
    
    def get_resource_levels(self):
        """Get current levels of all resources"""
        with self.session_factory() as session:
            resources = session.query(Resource).all()
            return {resource.id: {
                "name": resource.name,
                "capacity": resource.capacity,
                "current_level": resource.current_level
            } for resource in resources}
    
    def update_actuator_status(self, actuator_id, new_status):
        """Update an actuator's status and handle dependencies"""
        valid_statuses = ['open', 'close', 'changing state']
        if new_status not in valid_statuses:
            return {"error": f"Invalid status. Must be one of {valid_statuses}"}
        
        with self.session_factory() as session:
            # Start an explicit transaction
            session.begin()
            
            try:
                # Get the actuator with a row lock to prevent race conditions
                actuator = session.query(Actuator).filter(Actuator.id == actuator_id).with_for_update().first()
                if not actuator:
                    session.rollback()
                    return {"error": f"Actuator {actuator_id} not found"}
                
                # Store original status for verification
                original_status = actuator.status
                
                # Update actuator status
                actuator.status = new_status
                
                # If this is a valve, update linked pumps accordingly
                if actuator.type in ['water_valves', 'fertilizer_dispensers']:
                    self._update_linked_pumps(session, actuator, new_status)
                
                # Commit the transaction
                session.commit()
                
                telemetry_data = {}
                # Switch case to map status to ThingsBoard telemetry
                
                if actuator.status == 'open':
                    telemetry_data = {"deviceState": 1}
                elif actuator.status == 'close':
                    telemetry_data = {"deviceState": 0}
                else:
                    telemetry_data = {"deviceState": -1}
                
                # Sync with ThingsBoard
                self._sync_actuator_with_thingsboard(actuator.thingsboard_id, telemetry_data)
                
                # Verify the change by querying again
                with self.session_factory() as verify_session:
                    updated_actuator = verify_session.query(Actuator).filter(Actuator.id == actuator_id).first()
                    
                    if updated_actuator and updated_actuator.status == new_status:
                        # Change was successful
                        return {
                            **updated_actuator.to_dict(),
                            "status_change": {
                                "from": original_status,
                                "to": new_status,
                                "verified": True,
                                "thingsboard_synced": True
                            }
                        }
                    else:
                        # Change verification failed
                        return {
                            "error": "Failed to verify status change",
                            "actuator_id": actuator_id,
                            "requested_status": new_status,
                            "current_status": updated_actuator.status if updated_actuator else "unknown"
                        }
                    
            except Exception as e:
                # Rollback on any error
                session.rollback()
                return {"error": f"Failed to update actuator status: {str(e)}"}
            
    def _update_linked_pumps(self, session, valve, new_status):
        changed_pumps = []
        
        for pump in valve.linked_pumps:
            original_status = pump.status
            should_update = False
            
            if new_status == 'open':
                # If valve is opening, open the pump
                pump.status = 'open'
                should_update = True
            elif new_status == 'close':
                # If valve is closing, check if any other linked valves are still open
                all_valves_closed = True
                for linked_valve in pump.linked_valves:
                    if linked_valve.id != valve.id and linked_valve.status == 'open':
                        all_valves_closed = False
                        break
                
                if all_valves_closed:
                    pump.status = 'close'
                    should_update = True
            
            # Keep track of changed pumps for ThingsBoard sync
            if should_update and original_status != pump.status:
                changed_pumps.append(pump)
        
        # Update the pump status in the database
        session.commit()
        
        # Sync changed pumps with ThingsBoard
        for changed_pump in changed_pumps:
            with self.session_factory() as sync_session:
                pump = sync_session.query(Actuator).filter(Actuator.id == changed_pump.id).first()
                if pump:
                    # Switch case to map status to ThingsBoard telemetry
                    if pump.status == 'open':
                        telemetry_data = {"deviceState": 1}
                    elif pump.status == 'close':
                        telemetry_data = {"deviceState": 0}
                    else:
                        telemetry_data = {"deviceState": -1}
                    self._sync_actuator_with_thingsboard(changed_pump.thingsboard_id, telemetry_data)
    
    def _sync_actuator_with_thingsboard(self, actuator_id, telemetry_data):
        """Synchronize actuator state with ThingsBoard."""
        try:
            # Get JWT token for authentication
            jwt_token = get_jwt_token()
            if not jwt_token:
                return False
            
            # Get device token for the actuator
            device_token = get_device_token(jwt_token, actuator_id)
            if not device_token:
               print("[INFO]Device token not found on ThingsBoard.")
               return False
            
            print("[INFO]Device token found on ThingsBoard:", device_token)
            print("[INFO]Telemetry data to be sent:", telemetry_data)
            # Send telemetry data to ThingsBoard
            result = send_telemetry(device_token, telemetry_data)
            
            print("[INFO]Response from Thingsboard:", result)
            
            return result
        except Exception as e:
            import logging
            logging.error(f"Failed to sync actuator with ThingsBoard: {str(e)}")
            return False
    
    def get_resource_dependent_actuators(self, resource_id, include_related=True):
        """Get all actuators that depend on a specific resource"""
        with self.session_factory() as session:
            resource = session.query(Resource).filter(Resource.id == resource_id).options(
                joinedload(Resource.actuators)
            ).first()
            
            if not resource:
                return {"error": f"Resource {resource_id} not found"}
            
            return [actuator.to_dict(include_related=include_related) for actuator in resource.actuators]
            
    def create_irrigation_schedule(self, field_id, schedule_data):
        """
        Placeholder for creating irrigation schedules.
        In a real system, this would interact with a scheduling system.
        """
        return {
            "field_id": field_id,
            "schedule": schedule_data,
            "status": "created"
        }
    
    def update_resource_level(self, resource_id, new_level):
        """Update a resource's current level"""
        with self.session_factory() as session:
            resource = session.query(Resource).filter(Resource.id == resource_id).first()
            if not resource:
                return {"error": f"Resource {resource_id} not found"}
            
            # Store original level for verification
            original_level = resource.current_level
            
            # Update resource level in local database
            resource.current_level = new_level
            session.commit()
            
            # Sync with ThingsBoard
            self._sync_resource_with_thingsboard(resource.thingsboard_id, {
                "current_level": new_level,
                "percentage_full": (float(new_level) / float(resource.capacity)) * 100 if resource.capacity else 0
            })
            
            return {
                **resource.to_dict(),
                "level_change": {
                    "from": original_level,
                    "to": new_level,
                    "thingsboard_synced": True
                }
            }
    
    def _sync_resource_with_thingsboard(self, resource_id, telemetry_data):
        """Synchronize resource state with ThingsBoard."""
        try:
            # Get JWT token for authentication
            jwt_token = get_jwt_token()
            if not jwt_token:
                return False
            
            # Get device token for the resource
            device_token = get_device_token(jwt_token, resource_id)
            if not device_token:
                print("[INFO]Device token not found on ThingsBoard.")
                return False
            
            # Send telemetry data to ThingsBoard
            result = send_telemetry(device_token, telemetry_data)
            return result
        except Exception as e:
            import logging
            logging.error(f"Failed to sync resource with ThingsBoard: {str(e)}")
            return False
    
    # Updated method to sync sensors with ThingsBoard
    def sync_sensor_with_thingsboard(self, sensor_id, telemetry_data):
        """Sync a sensor's data with ThingsBoard"""
        with self.session_factory() as session:
            sensor = session.query(Sensor).filter(Sensor.id == sensor_id).first()
            if not sensor:
                return {"error": f"Sensor {sensor_id} not found"}
            
            try:
                # Get JWT token for authentication
                jwt_token = get_jwt_token()
                if not jwt_token:
                    return {"error": "Failed to authenticate with ThingsBoard"}
                
                # Get or create the device in ThingsBoard
                if not sensor.thingsboard_id:
                    device_data = {
                        "name": f"Sensor-{sensor.id}",
                        "type": sensor.type,
                        "label": f"{sensor.type.replace('_', ' ').title()} {sensor.id}",
                        "additionalInfo": {
                            "description": f"{sensor.type} sensor for field {sensor.field_id}",
                            "unit": sensor.unit
                        }
                    }
                    tb_device_id = create_or_update_device_on_thingsboard(jwt_token, device_data, "sensor")
                    if tb_device_id:
                        sensor.thingsboard_id = tb_device_id
                        session.commit()
                
                # Send telemetry to ThingsBoard
                device_token = get_device_token(jwt_token, sensor.thingsboard_id)
                if not device_token:
                    return {"error": "Failed to get device token from ThingsBoard"}
                
                result = send_telemetry(device_token, telemetry_data)
                return {
                    "sensor_id": sensor_id,
                    "thingsboard_id": sensor.thingsboard_id,
                    "telemetry": telemetry_data,
                    "status": "synced" if result else "failed"
                }
            except Exception as e:
                import logging
                logging.error(f"Failed to sync sensor with ThingsBoard: {str(e)}")
                return {"error": f"Failed to sync sensor: {str(e)}"}
    
    def sync_all_devices_with_thingsboard(self):
        """Create or update all devices in ThingsBoard."""
        jwt_token = get_jwt_token()
        if not jwt_token:
            return {"error": "Failed to authenticate with ThingsBoard"}
        
        results = {
            "sensors": [],
            "actuators": [],
            "resources": []
        }
        
        # Sync sensors
        with self.session_factory() as session:
            sensors = session.query(Sensor).all()
            for sensor in sensors:
                device_data = {
                    "name": f"Sensor-{sensor.id}",
                    "type": sensor.type,
                    "label": f"{sensor.type.replace('_', ' ').title()} {sensor.id}",
                    "additionalInfo": {
                        "description": f"{sensor.type} sensor for field {sensor.field_id}",
                        "unit": sensor.unit
                    }
                }
                
                tb_device_id = create_or_update_device_on_thingsboard(jwt_token, device_data, "sensor")
                if tb_device_id:
                    sensor.thingsboard_id = tb_device_id
                    session.commit()
                    
                    # Send initial telemetry (dummy data as example)
                    device_token = get_device_token(jwt_token, tb_device_id)
                    if device_token:
                        telemetry = {
                            "status": "active",
                            "battery": 100,
                            "lastReading": 0
                        }
                        send_telemetry(device_token, telemetry)
                    
                    results["sensors"].append({
                        "id": sensor.id,
                        "thingsboard_id": tb_device_id,
                        "status": "synced"
                    })
        
        # Sync actuators
        with self.session_factory() as session:
            actuators = session.query(Actuator).all()
            for actuator in actuators:
                device_data = {
                    "name": f"Actuator-{actuator.id}",
                    "type": actuator.type,
                    "label": f"{actuator.type.replace('_', ' ').title()} {actuator.id}",
                    "additionalInfo": {
                        "description": f"{actuator.subtype} {actuator.type}",
                        "operation_type": actuator.operation_type
                    }
                }
                
                tb_device_id = create_or_update_device_on_thingsboard(jwt_token, device_data, "actuator")
                if tb_device_id:
                    actuator.thingsboard_id = tb_device_id
                    session.commit()
                        
                    # Send initial telemetry
                    device_token = get_device_token(jwt_token, tb_device_id)
                    if device_token:
                        # Map status to device state
                        device_state = 1 if actuator.status == 'open' else 0 if actuator.status == 'close' else -1
                        telemetry = {
                            "deviceState": device_state,
                            "base_speed": actuator.base_speed
                        }
                        send_telemetry(device_token, telemetry)
                    
                    results["actuators"].append({
                        "id": actuator.id,
                        "thingsboard_id": tb_device_id,
                        "status": "synced"
                    })
        
        # Sync resources
        with self.session_factory() as session:
            resources = session.query(Resource).all()
            for resource in resources:
                device_data = {
                    "name": f"Resource-{resource.id}",
                    "type": "resource",
                    "label": f"{resource.name.replace('_', ' ').title()} Tank",
                    "additionalInfo": {
                        "description": f"{resource.content} storage tank",
                        "capacity": resource.capacity
                    }
                }
                
                tb_device_id = create_or_update_device_on_thingsboard(jwt_token, device_data, "resource")
                if tb_device_id:
                    resource.thingsboard_id = tb_device_id
                    session.commit()
                        
                    # Send initial telemetry
                    device_token = get_device_token(jwt_token, tb_device_id)
                    if device_token:
                        telemetry = {
                            "current_level": resource.current_level,
                            "percentage_full": (float(resource.current_level) / float(resource.capacity)) * 100 if resource.capacity else 0
                        }
                        send_telemetry(device_token, telemetry)
                    
                    results["resources"].append({
                        "id": resource.id,
                        "thingsboard_id": tb_device_id,
                        "status": "synced"
                    })
        
        return results