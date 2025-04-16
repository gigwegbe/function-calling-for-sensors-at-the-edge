
from sqlalchemy.orm import Session, relationship
from sqlalchemy import Column, String, Boolean, DateTime, Float, ForeignKey
from typing import Dict, List, Any, TypedDict, Optional
from datetime import datetime, timedelta
import threading
import os
import json
import time
import requests
from dotenv import load_dotenv
import paho.mqtt.client as mqtt

# Import your existing models and utils
from app.utils.db import Base
from app.utils.thingsboard import get_jwt_token, get_device_token, send_telemetry, create_or_update_device_on_thingsboard

# Import LangGraph components
from langgraph.graph import StateGraph, START, END
from langchain_community.chat_models import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage
from app.models.all_models import Resource, Actuator, ActuatorResource, IrrigationSession, SystemEvent

load_dotenv()
host = os.getenv('THINGSBOARD_HOST', 'localhost')

print("Thingsboard host:", host)

# Tank Farm Configuration - based on the provided model
TANK_FARM_CONFIG = {
    "tanks": [
        {"id": "T001", "name": "Tank 1", "max_capacity": 500, "units": "liter"},
        {"id": "T002", "name": "Tank 2", "max_capacity": 500, "units": "liter"},
        {"id": "T003", "name": "Tank 3", "max_capacity": 500, "units": "liter"},
        {"id": "T004", "name": "Tank 4", "max_capacity": 500, "units": "liter"},
        {"id": "T005", "name": "Tank 5", "max_capacity": 500, "units": "liter"}
    ],
    "mqtt_broker": {
        "host": host,
        "port": 1884,
        "topic": "v1/devices/me/telemetry"
    },
    "update_interval": 10  # minutes
}

jwt_token = get_jwt_token()  # Get ThingsBoard JWT token

class EnhancedActuatorControlState(TypedDict):
    """Enhanced state representation for the LangGraph workflow."""
    messages: List[Dict[str, str]]
    actuator_states: Dict[str, Dict[str, Any]]
    resource_states: Dict[str, Dict[str, Any]]
    sensor_values: Dict[str, Dict[str, Any]]
    user_request: str
    scenario_context: Optional[Dict[str, Any]]
    recommended_action: Optional[str]
    action_result: Optional[Dict[str, Any]]
    action_results: Optional[List[Dict[str, Any]]]
    action_plan: Optional[Dict[str, Any]]
    resource_impacts: Optional[Dict[str, Any]]
    recommendations: Optional[List[str]]
    error: Optional[str]


class TankFarmMonitor:
    """Service that monitors tank levels from the external tank farm system."""
    
    def __init__(self, db: Session, config=None):
        self.db = db
        self.config = config or TANK_FARM_CONFIG
        self.mqtt_client = None
        self.running = False
        self.thread = None
        
        # For storing latest tank data
        self.tank_data = {}
        
        # Initialize tanks in database if they don't exist
        self._initialize_tanks()
        
    def _initialize_tanks(self):
        """Initialize tank resources in the database based on config."""
        for tank_config in self.config["tanks"]:
            # Check if tank exists in the local database
            tank = self.db.query(Resource).filter(Resource.external_id == tank_config["id"]).first()

            # Prepare device data for ThingsBoard
            device_data = {
                "name": tank_config["name"],
                "type": "tank",
                "label": "Water Tank",
                "additionalInfo": {"description": f"Tank {tank_config['id']} for water storage"}
            }

            # Register or update the tank as a device on ThingsBoard
            thingsboard_id = create_or_update_device_on_thingsboard(jwt_token, device_data)

            if not thingsboard_id:
                print(f"Failed to create or update tank on ThingsBoard: {tank_config['name']}")
                continue

            if not tank:
                # Create new tank resource in the local database
                tank = Resource(
                    id=thingsboard_id, 
                    name=tank_config["name"],
                    type="water",
                    capacity=tank_config["max_capacity"],
                    units=tank_config["units"],
                    current_level=tank_config["max_capacity"] * 0.7,  # Default to 70% full
                    refill_threshold=20.0,  # Alert when below 20%
                    external_id=tank_config["id"]
                )
                self.db.add(tank)
                self.db.commit()
                print(f"Created tank resource in local database: {tank.name} ({tank.external_id})")
            else:
                # Update the local database with the ThingsBoard ID if necessary
                if tank.id != thingsboard_id:
                    tank.id = thingsboard_id
                    self.db.commit()
                    print(f"Updated local tank resource with ThingsBoard ID: {tank.name} ({tank.external_id})")

            # Send initial telemetry for the tank
            device_token = get_device_token(jwt_token, thingsboard_id)
            if device_token:
                telemetry_data = {
                    "currentLevel": tank.current_level,
                    "maxCapacity": tank.capacity,
                    "percentage": (tank.current_level / tank.capacity) * 100 if tank.capacity > 0 else 0,
                    "units": tank.units,
                    "lastUpdated": datetime.utcnow().isoformat()
                }
                send_telemetry(device_token, telemetry_data)
                print(f"Sent initial telemetry for {tank.name}")
        
        

                
            # Send initial telemetry for the tank
            device_token = get_device_token(jwt_token, thingsboard_id)
            if device_token:
                telemetry_data = {
                    "currentLevel": tank.current_level,
                    "maxCapacity": tank.capacity,
                    "percentage": (tank.current_level / tank.capacity) * 100 if tank.capacity > 0 else 0,
                    "units": tank.units,
                    "lastUpdated": datetime.utcnow().isoformat()
                }
                send_telemetry(device_token, telemetry_data)
                print(f"Sent initial telemetry for {tank.name}")
    
    def start_monitoring(self):
        """Start monitoring tank levels via MQTT."""
        if self.running:
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._monitor_worker)
        self.thread.daemon = True
        self.thread.start()
        
        # Also start MQTT client if needed
        self._setup_mqtt()
        
    def stop_monitoring(self):
        """Stop monitoring tank levels."""
        self.running = False
        if self.mqtt_client:
            self.mqtt_client.disconnect()
    
    def _setup_mqtt(self):
        """Set up MQTT client for listening to tank updates."""
        try:
            client = mqtt.Client()
    
            # Define callbacks
            def on_connect(client, userdata, flags, rc):
                print(f"Connected to MQTT broker with result code {rc}")
                for tank in self.config["tanks"]:
                    topic = f"{self.config['mqtt_broker']['topic']}/{tank['id']}"
                    client.subscribe(topic)
                    print(f"Subscribed to {topic}")
    
            def on_message(client, userdata, msg):
                try:
                    payload = json.loads(msg.payload.decode())
                    tank_id = msg.topic.split('/')[-1]
                    if "currentLevel" in payload:
                        self._update_tank_level(tank_id, payload["currentLevel"])
                        print(f"Updated tank {tank_id} level to {payload['currentLevel']} {payload.get('unit', 'liters')}")
                    
                        # Send acknowledgment
                        client.publish(
                            f"{self.config['mqtt_broker']['topic']}/ack",
                            json.dumps({"status": "ack", "tank_id": tank_id}),
                            qos=1
                        )
                        
                        # Forward telemetry to ThingsBoard if tank exists
                        tank = self.db.query(Resource).filter(Resource.external_id == tank_id).first()
                        if tank and tank.id:
                            jwt_token = get_jwt_token()
                            device_token = get_device_token(jwt_token, tank.id)
                            if device_token:
                                telemetry_data = {
                                    "currentLevel": tank.current_level,
                                    "percentage": (tank.current_level / tank.capacity) * 100 if tank.capacity > 0 else 0,
                                    "lastUpdated": datetime.utcnow().isoformat()
                                }
                                send_telemetry(device_token, telemetry_data)
                    
                    # Handle other payload data as needed
                    # For example, if you receive a refill recommendation
                    if "refillRecommendation" in payload:
                        tank = self.db.query(Resource).filter(Resource.external_id == tank_id).first()
                        if tank:
                            print(f"Refill recommendation for {tank.name}: {payload['refillRecommendation']} liters")
                            # Create a refill event
                            event = SystemEvent(
                                id=f"event_{int(time.time())}_{tank_id}",
                                event_type="refill_recommendation",
                                description=f"Refill recommendation for tank '{tank.name}'",
                                severity="info",
                                resource_id=tank.id
                            )
                            self.db.add(event)
                            self.db.commit()
                            print(f"Created refill event for {tank.name}")
                except Exception as e:
                    print(f"Error processing MQTT message: {e}")
    
            def on_disconnect(client, userdata, rc):
                print(f"Disconnected from MQTT broker with result code {rc}")
                # Try to reconnect if not shutting down
                if self.running:
                    print("Attempting to reconnect...")
                    time.sleep(5)
                    try:
                        client.reconnect()
                    except Exception as e:
                        print(f"Failed to reconnect: {e}")
    
            client.on_connect = on_connect
            client.on_message = on_message
            client.on_disconnect = on_disconnect
    
            # Increase connection timeout
            client.connect(self.config["mqtt_broker"]["host"], self.config["mqtt_broker"]["port"], keepalive=120)
    
            # Start the loop in a separate thread
            client.loop_start()
            self.mqtt_client = client
    
        except Exception as e:
            print(f"Failed to set up MQTT client: {e}")
    
    def _monitor_worker(self):
        """Background worker to periodically check tank levels."""
        while self.running:
            try:
                # Fallback to simulating tank updates if MQTT not working
                if not self.mqtt_client or not self.mqtt_client.is_connected():
                    self._simulate_tank_updates()
                
                # Check if any tanks need refilling
                self._check_refill_alerts()
                
            except Exception as e:
                print(f"Error in tank monitoring: {e}")
                
            # Sleep for a bit
            time.sleep(30)  # Check every 30 seconds
    
    def _simulate_tank_updates(self):
        """Simulate tank updates when MQTT is not available."""
        import random
        
        for tank_config in self.config["tanks"]:
            tank_id = tank_config["id"]
            # Get current tank from database
            tank = self.db.query(Resource).filter(Resource.external_id == tank_id).first()
            
            if tank:
                # Simulate some usage (decrease by 0-2%)
                usage = random.uniform(0, 0.02) * tank.capacity
                new_level = max(0, tank.current_level - usage)
                
                # Update tank level
                self._update_tank_level(tank_id, new_level)
                
                # Send telemetry for the simulated update
                if tank.id:
                    jwt_token = get_jwt_token()
                    device_token = get_device_token(jwt_token, tank.id)
                    if device_token:
                        telemetry_data = {
                            "currentLevel": new_level,
                            "percentage": (new_level / tank.capacity) * 100 if tank.capacity > 0 else 0,
                            "simulated": True,
                            "lastUpdated": datetime.utcnow().isoformat()
                        }
                        send_telemetry(device_token, telemetry_data)
    
    def _update_tank_level(self, tank_id, new_level):
        """Update tank level in database."""
        tank = self.db.query(Resource).filter(Resource.external_id == tank_id).first()
        
        if tank:
            old_level = tank.current_level
            tank.current_level = new_level
            tank.last_updated = datetime.utcnow()
            self.db.commit()
            
            # Store latest data
            self.tank_data[tank_id] = {
                "id": tank.id,
                "name": tank.name,
                "current_level": new_level,
                "capacity": tank.capacity,
                "percentage": (new_level / tank.capacity * 100) if tank.capacity > 0 else 0,
                "units": tank.units,
                "last_updated": tank.last_updated.isoformat()
            }
            
            # Log significant changes (more than 5%)
            if abs(old_level - new_level) > (tank.capacity * 0.05):
                print(f"Significant change in {tank.name}: {old_level} -> {new_level} {tank.units}")
    
    def _check_refill_alerts(self):
        """Check if any tanks need refilling and create alerts."""
        for tank_id, data in self.tank_data.items():
            tank = self.db.query(Resource).filter(Resource.external_id == tank_id).first()
            
            if not tank:
                continue
                
            # Check if below threshold
            percentage = (tank.current_level / tank.capacity * 100) if tank.capacity > 0 else 0
            if percentage < tank.refill_threshold:
                # Check if there's already an alert
                existing_alert = self.db.query(SystemEvent).filter(
                    SystemEvent.resource_id == tank.id,
                    SystemEvent.resolved == False,
                    SystemEvent.event_type == "resource_low"
                ).first()
                
                if not existing_alert:
                    # Create new alert
                    alert = SystemEvent(
                        id=f"event_{int(time.time())}_{tank_id}",
                        event_type="resource_low",
                        description=f"Water tank '{tank.name}' is below refill threshold ({tank.refill_threshold}%)",
                        severity="warning",
                        resource_id=tank.id
                    )
                    self.db.add(alert)
                    self.db.commit()
                    print(f"Created refill alert for {tank.name}: {percentage:.1f}% remaining")
    
    def get_tank_data(self):
        """Get current data for all tanks."""
        # Make sure we have the latest data
        for tank_config in self.config["tanks"]:
            tank_id = tank_config["id"]
            tank = self.db.query(Resource).filter(Resource.external_id == tank_id).first()
            
            if tank:
                self.tank_data[tank_id] = {
                    "id": tank.id,
                    "name": tank.name,
                    "current_level": tank.current_level,
                    "capacity": tank.capacity,
                    "percentage": (tank.current_level / tank.capacity * 100) if tank.capacity > 0 else 0,
                    "units": tank.units,
                    "last_updated": tank.last_updated.isoformat()
                }
                
        return self.tank_data


class IrrigationController:
    """Service that manages irrigation-specific logic."""
    
    def __init__(self, db: Session):
        self.db = db
        self.active_sessions = {}  # Track active irrigation sessions
    
    def start_irrigation(self, pump_id: str, valve_ids: List[str], tank_id: str) -> Dict[str, Any]:
        """Start an irrigation session."""
        # Get the components
        pump = self.db.query(Actuator).filter(Actuator.id == pump_id).first()
        tank = self.db.query(Resource).filter(Resource.id == tank_id).first()
        valves = self.db.query(Actuator).filter(Actuator.id.in_(valve_ids)).all()
        
        if not pump or not tank:
            return {"success": False, "error": "Pump or tank not found"}
            
        # Check if tank has enough water
        if tank.current_level < (tank.capacity * 0.05):  # 5% minimum
            return {"success": False, "error": "Water tank too low for irrigation"}
        
        # Activate the pump and valves in database
        pump.state = True
        for valve in valves:
            valve.state = True
        
        # Create a session record
        session_id = f"irrigation_{int(time.time())}"
        session = IrrigationSession(
            id=session_id,
            start_time=datetime.utcnow(),
            source_tank_id=tank.id,
            primary_pump_id=pump.id,
            status="active",
            notes=f"Irrigation using {len(valve_ids)} valves"
        )
        self.db.add(session)
        
        # Track session in memory
        self.active_sessions[session_id] = {
            "start_time": datetime.utcnow(),
            "pump_id": pump_id,
            "valve_ids": valve_ids,
            "tank_id": tank_id,
            "initial_level": tank.current_level,
            "flow_rate": pump.flow_rate,
            "power_usage": pump.power_consumption  # Track power usage
        }
        
        self.db.commit()
        
        # Send telemetry to ThingsBoard for the pump and valves
        try:
            jwt_token = get_jwt_token()
            
            # Send pump state telemetry
            if pump.id:
                device_token = get_device_token(jwt_token, pump.id)
                if device_token:
                    telemetry_data = {
                        "state": "ON",
                        "flowRate": pump.flow_rate,
                        "powerConsumption": pump.power_consumption,
                        "sessionId": session_id,
                        "lastUpdated": datetime.utcnow().isoformat()
                    }
                    send_telemetry(device_token, telemetry_data)
                    
            # Send valve state telemetry
            for valve in valves:
                if valve.id:
                    device_token = get_device_token(jwt_token, valve.id)
                    if device_token:
                        telemetry_data = {
                            "state": "OPEN",
                            "flowRate": valve.flow_rate,
                            "sessionId": session_id,
                            "lastUpdated": datetime.utcnow().isoformat()
                        }
                        send_telemetry(device_token, telemetry_data)
        except Exception as e:
            print(f"Error sending telemetry: {str(e)}")
        
        return {
            "success": True, 
            "session_id": session_id, 
            "estimated_runtime": self._calculate_runtime(tank, pump),
            "power_consumption": pump.power_consumption
        }
    
    def stop_irrigation(self, session_id: str) -> Dict[str, Any]:
        """Stop an irrigation session and calculate water usage."""
        if session_id not in self.active_sessions:
            return {"success": False, "error": "No active session found"}
            
        session_data = self.active_sessions[session_id]
        session = self.db.query(IrrigationSession).filter(IrrigationSession.id == session_id).first()
        
        if not session:
            return {"success": False, "error": "Session record not found"}
            
        # Calculate elapsed time and water used
        start_time = session_data["start_time"]
        end_time = datetime.utcnow()
        elapsed_time = (end_time - start_time).total_seconds() / 60  # minutes
        
        # Calculate water used and power consumed
        flow_rate = session_data["flow_rate"]  # liters per minute
        water_used = flow_rate * elapsed_time
        
        power_consumption = session_data.get("power_usage", 0)  # watts
        energy_consumed = (power_consumption * elapsed_time) / 60  # watt-hours
        
        # Deactivate the pump and valves
        pump = self.db.query(Actuator).filter(Actuator.id == session_data["pump_id"]).first()
        if pump:
            pump.state = False
            
        valves = self.db.query(Actuator).filter(Actuator.id.in_(session_data["valve_ids"])).all()
        for valve in valves:
            valve.state = False
        
        # Update session record
        session.end_time = end_time
        session.duration_minutes = elapsed_time
        session.water_used = water_used
        session.energy_consumed = energy_consumed  # Add this field to your model if not present
        session.status = "completed"
        
        # Update tank level
        tank = self.db.query(Resource).filter(Resource.id == session_data["tank_id"]).first()
        if tank:
            tank.current_level = max(0, tank.current_level - water_used)
            tank.last_updated = datetime.utcnow()
            
            # Check if we need to create a refill event
            if tank.current_level < (tank.capacity * (tank.refill_threshold / 100)):
                self._create_refill_event(tank)
        
        self.db.commit()
        
        # Send telemetry to ThingsBoard
        try:
            jwt_token = get_jwt_token()
            
            # Send pump state telemetry
            if pump and pump.id:
                device_token = get_device_token(jwt_token, pump.id)
                if device_token:
                    telemetry_data = {
                        "state": "OFF",
                        "lastSession": session_id,
                        "lastWaterUsed": water_used,
                        "lastEnergyConsumed": energy_consumed,
                        "lastUpdated": datetime.utcnow().isoformat()
                    }
                    send_telemetry(device_token, telemetry_data)
                    
            # Send valve state telemetry
            for valve in valves:
                if valve.id:
                    device_token = get_device_token(jwt_token, valve.id)
                    if device_token:
                        telemetry_data = {
                            "state": "CLOSED",
                            "lastSession": session_id,
                            "lastUpdated": datetime.utcnow().isoformat()
                        }
                        send_telemetry(device_token, telemetry_data)
                        
            # Send tank update telemetry
            if tank and tank.id:
                device_token = get_device_token(jwt_token, tank.id)
                if device_token:
                    telemetry_data = {
                        "currentLevel": tank.current_level,
                        "percentage": (tank.current_level / tank.capacity * 100) if tank.capacity > 0 else 0,
                        "lastUpdated": datetime.utcnow().isoformat()
                    }
                    send_telemetry(device_token, telemetry_data)
        except Exception as e:
            print(f"Error sending telemetry: {str(e)}")
        
        # Clean up the session
        del self.active_sessions[session_id]
        
        return {
            "success": True,
            "water_used": water_used,
            "duration_minutes": elapsed_time,
            "energy_consumed": energy_consumed,
            "tank_level": tank.current_level if tank else None,
            "tank_percentage": (tank.current_level / tank.capacity * 100) if tank else None
        }
    
    def _calculate_runtime(self, tank: Resource, pump: Actuator) -> float:
        """Calculate how long irrigation can run based on water level and flow rate."""
        if pump.flow_rate <= 0:
            return 0
            
        available_water = tank.current_level
        runtime_minutes = available_water / pump.flow_rate
        return runtime_minutes
    
    def _create_refill_event(self, tank: Resource):
        """Create a system event for tank refill recommendation."""
        event = SystemEvent(
            id=f"event_{int(time.time())}",
            event_type="resource_low",
            description=f"Water tank '{tank.name}' is below refill threshold ({tank.refill_threshold}%)",
            severity="warning",
            resource_id=tank.id
        )
        self.db.add(event)
        self.db.commit()
        
    def get_pending_recommendations(self) -> List[Dict[str, Any]]:
        """Get pending system recommendations."""
        events = self.db.query(SystemEvent).filter(
            SystemEvent.resolved == False
        ).order_by(SystemEvent.timestamp.desc()).all()
        
        recommendations = []
        for event in events:
            if event.event_type == "resource_low" and event.resource_id:
                resource = self.db.query(Resource).filter(Resource.id == event.resource_id).first()
                if resource:
                    recommendations.append({
                        "event_id": event.id,
                        "type": "refill",
                        "resource_name": resource.name,
                        "resource_type": resource.type,
                        "current_level": resource.current_level,
                        "capacity": resource.capacity,
                        "percentage": (resource.current_level / resource.capacity) * 100 if resource.capacity > 0 else 0,
                        "timestamp": event.timestamp.isoformat()
                    })
                    
        return recommendations
    
    def get_water_usage_stats(self, days=7) -> Dict[str, Any]:
        """Get water usage statistics for the past X days."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Get completed irrigation sessions
        sessions = self.db.query(IrrigationSession).filter(
            IrrigationSession.status == "completed",
            IrrigationSession.end_time >= cutoff_date
        ).all()
        
        # Calculate totals
        total_water = sum(session.water_used for session in sessions if session.water_used)
        total_time = sum(session.duration_minutes for session in sessions if session.duration_minutes)
        total_energy = sum(getattr(session, 'energy_consumed', 0) for session in sessions)
        
        # Calculate daily averages
        daily_usage = {}
        for session in sessions:
            if not session.end_time or not session.water_used:
                continue
                
            day_key = session.end_time.strftime("%Y-%m-%d")
            if day_key not in daily_usage:
                daily_usage[day_key] = {
                    "water_used": 0,
                    "duration_minutes": 0,
                    "energy_consumed": 0,
                    "session_count": 0
                }
                
            daily_usage[day_key]["water_used"] += session.water_used
            daily_usage[day_key]["duration_minutes"] += session.duration_minutes
            daily_usage[day_key]["energy_consumed"] += getattr(session, 'energy_consumed', 0)
            daily_usage[day_key]["session_count"] += 1
        
        return {
            "total_water_used": total_water,
            "total_duration_minutes": total_time,
            "total_energy_consumed": total_energy,
            "session_count": len(sessions),
            "daily_breakdown": daily_usage
        }
        
    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Get information about active irrigation sessions."""
        active_session_info = []
        
        for session_id, data in self.active_sessions.items():
            # Get current elapsed time
            start_time = data["start_time"]
            current_time = datetime.utcnow()
            elapsed_minutes = (current_time - start_time).total_seconds() / 60
            
            # Calculate estimated water used so far
            flow_rate = data["flow_rate"]
            estimated_water_used = flow_rate * elapsed_minutes
            
            # Get power consumption
            power_consumption = data.get("power_usage", 0)
            estimated_energy = (power_consumption * elapsed_minutes) / 60  # watt-hours
            
            # Get component info  
            pump = self.db.query(Actuator).filter(Actuator.id == data["pump_id"]).first()
            tank = self.db.query(Resource).filter(Resource.id == data["tank_id"]).first()
            
            active_session_info.append({
                "session_id": session_id,
                "start_time": start_time.isoformat(),
                "elapsed_minutes": elapsed_minutes,
                "pump_name": pump.name if pump else "Unknown",
                "tank_name": tank.name if tank else "Unknown",
                "valve_count": len(data["valve_ids"]),
                "estimated_water_used": estimated_water_used,
                "estimated_energy_used": estimated_energy,
                "flow_rate": flow_rate
            })
            
        return active_session_info
    
class TankFarmActuatorLLMService:
    """Enhanced service for managing tank farm resources through LLM-powered interactions."""
    
    def __init__(self, db: Session, api_key: str = None):
        self.db = db
        self.api_key = api_key or os.environ.get("OPENAI_PROJECT_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
            
        self.llm = ChatOpenAI(api_key=self.api_key, temperature=0.2)
        self.actuator_graph = self._build_graph()
        
        # Resource management
        self.tank_monitor = TankFarmMonitor(db)
        self.irrigation_controller = IrrigationController(db)
        
        # Monitoring
        self.monitoring_lock = threading.Lock()
        self.paused_actuators = {}
        
        # Initialize
        self._initialize_farm_components()
        
        # Start monitoring
        self.tank_monitor.start_monitoring()
        
    def _initialize_farm_components(self):
        """Initialize farm components if they don't exist."""
        # Check if we need to create sample pumps and valves
        pumps = self.db.query(Actuator).filter(Actuator.type == "pump").all()
        valves = self.db.query(Actuator).filter(Actuator.type == "valve").all()
    
        # Create pumps if needed
        if not pumps:
            for i in range(3):  # Create 3 pumps
                pump = Actuator(
                    id=f"pump_{int(time.time())}_{i}",
                    name=f"Irrigation Pump {i+1}",
                    type="pump",
                    location="Field",  # Ensure this matches the new column
                    flow_rate=10.0,  # 10 liters per minute
                    power_consumption=500.0,  # 500 watts
                    state=False,
                    monitoring_active=True
                )
                self.db.add(pump)
                print(f"Created pump: {pump.name} ({pump.id})")

            self.db.commit()
            pumps = self.db.query(Actuator).filter(Actuator.type == "pump").all()
        
        # Create valves if needed
        if not valves:
            for i in range(5):  # Create 5 valves
                valve = Actuator(
                    id=f"valve_{int(time.time())}_{i}",
                    name=f"Field Valve {i+1}",
                    type="valve",
                    location=f"Field Section {i+1}",
                    flow_rate=8.0,  # 8 liters per minute when fully open
                    state=False,
                    monitoring_active=True
                )
                self.db.add(valve)
                print(f"Created valve: {valve.name} ({valve.id})")
                
            self.db.commit()
            valves = self.db.query(Actuator).filter(Actuator.type == "valve").all()
            
        # Link pumps to tanks (create connections)
        tanks = self.db.query(Resource).filter(Resource.type == "water").all()
        
        if tanks and pumps:
            # Link each pump to a tank
            for i, pump in enumerate(pumps):
                # Find corresponding tank (or use first one if not enough tanks)
                tank_index = min(i, len(tanks) - 1)
                tank = tanks[tank_index]
                
                # Check if connection exists
                connection = self.db.query(ActuatorResource).filter(
                    ActuatorResource.actuator_id == pump.id,
                    ActuatorResource.resource_id == tank.id
                ).first()
                
                if not connection:
                    connection = ActuatorResource(
                        id=f"conn_{int(time.time())}_{i}",
                        actuator_id=pump.id,
                        resource_id=tank.id,
                        relationship_type="consumes"
                    )
                    self.db.add(connection)
                    print(f"Created connection: Pump {pump.name} consumes from {tank.name}")
            
            self.db.commit()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine for actuator control."""
        workflow = StateGraph(EnhancedActuatorControlState)
        
        # Define the nodes
        workflow.add_node("analyze_request", self._analyze_request)
        workflow.add_node("identify_scenario", self._identify_scenario)
        workflow.add_node("fetch_context", self._fetch_context)
        workflow.add_node("plan_actions", self._plan_actions)
        workflow.add_node("execute_actions", self._execute_actions)
        workflow.add_node("analyze_impacts", self._analyze_impacts)
        workflow.add_node("format_response", self._format_response)
        
        # Define the edges
        workflow.add_edge(START, "analyze_request")
        workflow.add_edge("analyze_request", "identify_scenario")
        workflow.add_edge("identify_scenario", "fetch_context")
        workflow.add_edge("fetch_context", "plan_actions")
        workflow.add_edge("plan_actions", "execute_actions")
        workflow.add_edge("execute_actions", "analyze_impacts")
        workflow.add_edge("analyze_impacts", "format_response")
        workflow.add_edge("format_response", END)
        
        # Compile the graph
        return workflow.compile()

    def _analyze_request(self, state: EnhancedActuatorControlState) -> EnhancedActuatorControlState:
        """Use LLM to understand user request and determine intent."""
        system_prompt = """
        You are an intelligent assistant for a farm irrigation system that uses water from a tank farm.
        Your role is to interpret user requests related to irrigation, water tanks, pumps, valves, and monitoring.
        
        Available operations:
        - Check tank levels and water resources
        - Start or stop irrigation for specific field sections
        - Control pumps and valves
        - Monitor water usage and consumption rates
        - Get status reports on the irrigation system
        - Manage refilling of water tanks
        - Track historical water usage
        
        Analyze the user's request and determine which operation they want to perform.
        """
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"User request: {state['user_request']}")
        ]
        
        response = self.llm.invoke(messages)
        
        # Parse the intent from the LLM response
        state["recommended_action"] = response.content
        return state

    def _identify_scenario(self, state: EnhancedActuatorControlState) -> EnhancedActuatorControlState:
        """Identify the scenario context from the user request."""
        scenario_prompt = f"""
        Based on the user request: "{state['user_request']}"
        
        Determine if this request fits into one of these scenarios:
        1. Irrigation Control: Starting/stopping irrigation in specific fields
        2. Resource Monitoring: Checking tank levels or water usage
        3. System Configuration: Setting up or modifying components
        4. Resource Management: Managing tank refilling or resource allocation
        5. Status Reporting: Getting information about current system state
        
        Respond with JSON containing:
        - scenario: One of ["irrigation_control", "resource_monitoring", "system_configuration", "resource_management", "status_reporting"]
        - additional_context: Any additional context or parameters extracted from the request
        """
        
        response = self.llm.invoke([HumanMessage(content=scenario_prompt)])
        
        try:
            scenario_data = json.loads(response.content)
            state["scenario_context"] = scenario_data
        except json.JSONDecodeError:
            state["error"] = "Failed to parse scenario context as JSON"
        
        return state

    def _fetch_context(self, state: EnhancedActuatorControlState) -> EnhancedActuatorControlState:
        """Fetch relevant context based on the identified scenario."""
        # Fetch tank and actuator data
        state["resource_states"] = self.tank_monitor.get_tank_data()
        state["actuator_states"] = {
            actuator.id: {
                "id": actuator.id,
                "name": actuator.name,
                "type": actuator.type,
                "state": actuator.state,
                "monitoring_active": actuator.monitoring_active
            }
            for actuator in self.db.query(Actuator).all()
        }
        return state

    
    # Additional methods needed for TankFarmActuatorLLMService

    def _plan_actions(self, state: EnhancedActuatorControlState) -> EnhancedActuatorControlState:
        """Plan actions based on scenario and context."""
        scenario = state.get("scenario_context", {}).get("scenario", "status_reporting")
        
        plan_prompt = f"""
        Based on the user request: "{state['user_request']}"
        Scenario identified: {scenario}
        
        Tank Resources Available:
        {json.dumps(state['resource_states'], indent=2)}
        
        Actuators Available:
        {json.dumps(state['actuator_states'], indent=2)}
        
        Create a plan of actions needed to fulfill this request. The plan should include:
        1. Main objective
        2. Required steps in sequence
        3. Resources affected
        4. Actuators to control
        
        Respond with valid JSON containing:
        - objective: Summary of what needs to be done
        - steps: Array of action steps, each with "description" and "action_type"
        - resources: Array of resource IDs that will be affected
        - actuators: Array of actuator IDs that need to be controlled 
        - parameters: Any additional parameters needed for execution
        """
        
        response = self.llm.invoke([HumanMessage(content=plan_prompt)])
        
        try:
            action_plan = json.loads(response.content)
            state["action_plan"] = action_plan
        except json.JSONDecodeError:
            state["error"] = "Failed to parse action plan as JSON"
            
        return state

    def _execute_actions(self, state: EnhancedActuatorControlState) -> EnhancedActuatorControlState:
        """Execute the planned actions based on scenario."""
        action_plan = state.get("action_plan", {})
        scenario = state.get("scenario_context", {}).get("scenario", "status_reporting")
        
        # Initialize results list
        action_results = []
        
        try:
            # Handle different scenarios
            if scenario == "irrigation_control":
                action_results.append(self._handle_irrigation_control(action_plan))
                
            elif scenario == "resource_monitoring":
                action_results.append(self._handle_resource_monitoring(action_plan))
                
            elif scenario == "resource_management":
                action_results.append(self._handle_resource_management(action_plan))
                
            elif scenario == "system_configuration":
                action_results.append(self._handle_system_configuration(action_plan))
                
            else:  # status_reporting or fallback
                action_results.append(self._handle_status_reporting(action_plan))
                
            state["action_results"] = action_results
            
        except Exception as e:
            state["error"] = f"Error executing actions: {str(e)}"
            
        return state

    def _handle_irrigation_control(self, action_plan: dict) -> dict:
        """Handle irrigation control scenarios."""
        objective = action_plan.get("objective", "")
        actuator_ids = action_plan.get("actuators", [])
        parameters = action_plan.get("parameters", {})
        
        # Determine if starting or stopping irrigation
        if "start" in objective.lower():
            # Extract pump, valves and tank from parameters
            pump_id = next((act for act in actuator_ids if "pump" in act), None)
            valve_ids = [act for act in actuator_ids if "valve" in act]
            tank_id = parameters.get("tank_id") or action_plan.get("resources", [""])[0]
            
            if pump_id and valve_ids and tank_id:
                result = self.irrigation_controller.start_irrigation(pump_id, valve_ids, tank_id)
                return {
                    "action": "start_irrigation",
                    "pump": pump_id,
                    "valves": valve_ids,
                    "tank": tank_id,
                    "result": result
                }
            else:
                return {"action": "start_irrigation", "error": "Missing required components"}
                
        elif "stop" in objective.lower():
            # Get session ID from parameters
            session_id = parameters.get("session_id")
            
            if session_id:
                result = self.irrigation_controller.stop_irrigation(session_id)
                return {
                    "action": "stop_irrigation",
                    "session_id": session_id,
                    "result": result
                }
            else:
                # Stop all active sessions
                results = []
                for session_id in list(self.irrigation_controller.active_sessions.keys()):
                    result = self.irrigation_controller.stop_irrigation(session_id)
                    results.append({"session_id": session_id, "result": result})
                    
                return {
                    "action": "stop_all_irrigation",
                    "results": results
                }
        
        return {"action": "irrigation_control", "status": "no_action_taken"}

    def _handle_resource_monitoring(self, action_plan: dict) -> dict:
        """Handle resource monitoring scenarios."""
        resources = action_plan.get("resources", [])
        parameters = action_plan.get("parameters", {})
        
        # Get tank data
        tank_data = self.tank_monitor.get_tank_data()
        
        # If specific resources requested, filter data
        if resources:
            tank_data = {k: v for k, v in tank_data.items() if k in resources or v["id"] in resources}
        
        # Get water usage stats if requested
        if "usage" in action_plan.get("objective", "").lower():
            days = parameters.get("days", 7)
            usage_stats = self.irrigation_controller.get_water_usage_stats(days)
            return {
                "action": "water_usage_stats",
                "data": usage_stats,
                "period_days": days
            }
        
        return {
            "action": "resource_monitoring",
            "data": tank_data
        }

    def _handle_resource_management(self, action_plan: dict) -> dict:
        """Handle resource management scenarios like refilling tanks."""
        objective = action_plan.get("objective", "").lower()
        resources = action_plan.get("resources", [])
        parameters = action_plan.get("parameters", {})
        
        if "refill" in objective:
            # Handle tank refilling
            refill_amount = parameters.get("refill_amount", 0)
            tank_id = resources[0] if resources else None
            
            if tank_id and refill_amount > 0:
                # Get the tank resource
                tank = None
                for ext_id, tank_data in self.tank_monitor.get_tank_data().items():
                    if ext_id == tank_id or tank_data["id"] == tank_id:
                        tank = self.db.query(Resource).filter(Resource.id == tank_data["id"]).first()
                        break
                
                if tank:
                    # Calculate new level, not exceeding capacity
                    old_level = tank.current_level
                    new_level = min(tank.capacity, old_level + refill_amount)
                    
                    # Update tank level
                    tank.current_level = new_level
                    tank.last_updated = datetime.utcnow()
                    self.db.commit()
                    
                    # Clear any refill alerts for this tank
                    alerts = self.db.query(SystemEvent).filter(
                        SystemEvent.resource_id == tank.id,
                        SystemEvent.resolved == False,
                        SystemEvent.event_type == "resource_low"
                    ).all()
                    
                    for alert in alerts:
                        alert.resolved = True
                        alert.description += f" - Resolved: Tank refilled on {datetime.utcnow().isoformat()}"
                    
                    self.db.commit()
                    
                    return {
                        "action": "refill_tank",
                        "tank_id": tank.id,
                        "tank_name": tank.name,
                        "old_level": old_level,
                        "added_amount": new_level - old_level,
                        "new_level": new_level,
                        "capacity": tank.capacity,
                        "new_percentage": (new_level / tank.capacity * 100) if tank.capacity > 0 else 0
                    }
        
        # Get pending recommendations as default
        recommendations = self.irrigation_controller.get_pending_recommendations()
        return {
            "action": "resource_management_report",
            "recommendations": recommendations
        }

    def _handle_system_configuration(self, action_plan: dict) -> dict:
        """Handle system configuration scenarios."""
        objective = action_plan.get("objective", "").lower()
        actuator_ids = action_plan.get("actuators", [])
        parameters = action_plan.get("parameters", {})
        
        if "create" in objective and "actuator" in objective:
            # Create new actuator
            actuator_data = {
                "name": parameters.get("name", "New Actuator"),
                "type": parameters.get("type", "valve"),
                "location": parameters.get("location", "Field"),
                "flow_rate": float(parameters.get("flow_rate", 8.0)),
                "state": False,
                "monitoring_active": True
            }
            
            new_actuator = Actuator(
                id=f"{actuator_data['type']}_{int(time.time())}",
                **actuator_data
            )
            
            self.db.add(new_actuator)
            self.db.commit()
            
            return {
                "action": "create_actuator",
                "actuator_id": new_actuator.id,
                "actuator_name": new_actuator.name,
                "actuator_type": new_actuator.type
            }
        
        elif "update" in objective and actuator_ids:
            # Update existing actuator
            actuator_id = actuator_ids[0]
            actuator = self.db.query(Actuator).filter(Actuator.id == actuator_id).first()
            
            if actuator:
                # Update fields
                for key, value in parameters.items():
                    if hasattr(actuator, key):
                        setattr(actuator, key, value)
                
                self.db.commit()
                
                return {
                    "action": "update_actuator",
                    "actuator_id": actuator.id,
                    "actuator_name": actuator.name,
                    "updated_fields": list(parameters.keys())
                }
        
        # Default: get system configuration
        actuators = self.db.query(Actuator).all()
        resources = self.db.query(Resource).all()
        
        return {
            "action": "system_configuration_report",
            "actuator_count": len(actuators),
            "resource_count": len(resources),
            "components": {
                "pumps": len([a for a in actuators if a.type == "pump"]),
                "valves": len([a for a in actuators if a.type == "valve"]),
                "tanks": len([r for r in resources if r.type == "water"])
            }
        }

    def _handle_status_reporting(self, action_plan: dict) -> dict:
        """Handle status reporting scenarios."""
        # Get system-wide status
        tank_data = self.tank_monitor.get_tank_data()
        
        # Get active irrigation sessions
        active_sessions = len(self.irrigation_controller.active_sessions)
        
        # Get actuator states
        pumps = self.db.query(Actuator).filter(Actuator.type == "pump").all()
        valves = self.db.query(Actuator).filter(Actuator.type == "valve").all()
        
        pump_states = [{"id": p.id, "name": p.name, "state": p.state} for p in pumps]
        valve_states = [{"id": v.id, "name": v.name, "state": v.state} for v in valves]
        
        # Get pending recommendations
        recommendations = self.irrigation_controller.get_pending_recommendations()
        
        return {
            "action": "system_status_report",
            "tank_count": len(tank_data),
            "total_capacity": sum(t["capacity"] for t in tank_data.values()),
            "current_water_level": sum(t["current_level"] for t in tank_data.values()),
            "active_irrigation_sessions": active_sessions,
            "active_pumps": sum(1 for p in pumps if p.state),
            "active_valves": sum(1 for v in valves if v.state),
            "pending_recommendations": len(recommendations)
        }

    def _analyze_impacts(self, state: EnhancedActuatorControlState) -> EnhancedActuatorControlState:
        """Analyze the impacts of executed actions on resources."""
        action_results = state.get("action_results", [])
        scenario = state.get("scenario_context", {}).get("scenario", "")
        
        # Skip detailed analysis for simple reporting
        if scenario == "status_reporting" or not action_results:
            return state
        
        # Get updated resource states
        updated_resources = {}
        for tank_id, tank_data in self.tank_monitor.get_tank_data().items():
            updated_resources[tank_id] = tank_data
        
        # Calculate changes
        resource_impacts = {
            "water_level_changes": {},
            "recommendations": []
        }
        
        # Check for significant changes in tank levels
        original_resources = state.get("resource_states", {})
        for tank_id, updated_data in updated_resources.items():
            if tank_id in original_resources:
                original_level = original_resources[tank_id]["current_level"]
                current_level = updated_data["current_level"]
                
                if original_level != current_level:
                    change = current_level - original_level
                    percentage = (current_level / updated_data["capacity"] * 100) if updated_data["capacity"] > 0 else 0
                    
                    resource_impacts["water_level_changes"][tank_id] = {
                        "tank_name": updated_data["name"],
                        "change": change,
                        "percentage_remaining": percentage,
                        "units": updated_data["units"]
                    }
                    
                    # Add recommendation if tank low
                    if percentage < 20:  # Arbitrary threshold
                        resource_impacts["recommendations"].append(
                            f"Tank {updated_data['name']} is low ({percentage:.1f}% remaining). Consider refilling soon."
                        )
        
        # Add water usage stats for irrigation actions
        for result in action_results:
            if result.get("action") in ["start_irrigation", "stop_irrigation", "stop_all_irrigation"]:
                usage_stats = self.irrigation_controller.get_water_usage_stats(1)  # Today's stats
                resource_impacts["today_usage_stats"] = usage_stats
                break
        
        state["resource_impacts"] = resource_impacts
        
        # Add recommendations
        recommendations = self.irrigation_controller.get_pending_recommendations()
        if recommendations:
            state["recommendations"] = [f"Refill tank {r['resource_name']} ({r['percentage']:.1f}% remaining)" 
                                    for r in recommendations]
        
        return state

    def _format_response(self, state: EnhancedActuatorControlState) -> EnhancedActuatorControlState:
        """Format the final response to return to the user."""
        # Use the LLM to generate a helpful, natural language response
        format_prompt = f"""
        User request: "{state['user_request']}"
        
        Action results: {json.dumps(state.get('action_results', []), indent=2)}
        
        Resource impacts: {json.dumps(state.get('resource_impacts', {}), indent=2)}
        
        Recommendations: {json.dumps(state.get('recommendations', []), indent=2)}
        
        Error (if any): {state.get('error', 'None')}
        
        Please provide a helpful, conversational response to the user that explains what was done
        and the current state of their farm irrigation system. Include any relevant information about
        tank levels, water usage, and recommendations. Keep it friendly, practical and informative.
        """
        
        response = self.llm.invoke([HumanMessage(content=format_prompt)])
        
        # Update the messages list with the assistant's response
        state["messages"].append({"role": "assistant", "content": response.content})
        return state

    def process_user_request(self, user_message: str) -> str:
        """Process a user request and return a response."""
        # Initialize the state
        initial_state = EnhancedActuatorControlState(
            messages=[{"role": "user", "content": user_message}],
            actuator_states={},
            resource_states={},
            sensor_values={},
            user_request=user_message,
            scenario_context=None,
            recommended_action=None,
            action_result=None,
            action_results=None,
            action_plan=None,
            resource_impacts=None,
            recommendations=None,
            error=None
        )
        
        # Execute the workflow
        try:
            final_state = self.actuator_graph.invoke(initial_state)
            return final_state["messages"][-1]["content"]
        except Exception as e:
            return f"Sorry, I encountered an error processing your request: {str(e)}"