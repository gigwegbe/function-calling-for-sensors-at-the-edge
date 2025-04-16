import argparse
import os
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import our components
from app.utils.db import Base
from app.services.actuator_llm_service import ActuatorLLMService
from app.models.actuator import Actuator
from app.models.sensor import Sensor

def setup_demo_database():
    """Set up a demo SQLite database with some initial data."""
    # Create an SQLite database in memory
    engine = create_engine("sqlite:///actuator_demo.db")
    Base.metadata.create_all(engine)
    
    # Create a session
    Session = sessionmaker(bind=engine)
    db = Session()
    
    # Create some demo actuators
    demo_actuators = [
        {
            "id": "irrigation-pump-001",
            "name": "Irrigation Pump",
            "type": "pump",
            "label": "Main Irrigation Pump",
            "state": False,
            "monitoring_active": True,
            "additionalInfo": {"location": "Field A", "max_flow_rate": "200L/min"}
        },
        {
            "id": "greenhouse-fan-001",
            "name": "Greenhouse Fan",
            "type": "fan",
            "label": "Greenhouse Cooling Fan",
            "state": True,
            "monitoring_active": True,
            "additionalInfo": {"location": "Greenhouse 1", "power": "120W"}
        },
        {
            "id": "water-valve-001",
            "name": "Water Valve",
            "type": "valve",
            "label": "Main Water Valve",
            "state": True,
            "monitoring_active": True,
            "additionalInfo": {"location": "Main Line", "diameter": "1.5 inches"}
        }
    ]
    
    # Create some demo sensors
    demo_sensors = [
        {
            "id": "soil-moisture-001",
            "name": "Soil Moisture Sensor",
            "type": "moisture",
            "keys": ["moisture", "temperature"],
            "additionalInfo": {"location": "Field A", "depth": "10cm"}
        },
        {
            "id": "temperature-001",
            "name": "Temperature Sensor",
            "type": "temperature",
            "keys": ["temperature", "humidity"],
            "additionalInfo": {"location": "Greenhouse 1", "model": "DHT22"}
        }
    ]
    
    # Add actuators to the database
    for actuator_data in demo_actuators:
        actuator = Actuator(**actuator_data)
        db.add(actuator)
    
    # Add sensors to the database
    for sensor_data in demo_sensors:
        sensor = Sensor(**sensor_data)
        db.add(sensor)
    
    # Connect sensors to actuators
    # Irrigation pump monitors soil moisture
    irrigation_pump = db.query(Actuator).filter(Actuator.id == "irrigation-pump-001").first()
    soil_moisture = db.query(Sensor).filter(Sensor.id == "soil-moisture-001").first()
    irrigation_pump.sensors.append(soil_moisture)
    
    # Greenhouse fan monitors temperature
    greenhouse_fan = db.query(Actuator).filter(Actuator.id == "greenhouse-fan-001").first()
    temperature = db.query(Sensor).filter(Sensor.id == "temperature-001").first()
    greenhouse_fan.sensors.append(temperature)
    
    db.commit()
    
    return engine, db

def run_demo(db):
    """Run a demonstration of the ActuatorLLMService."""
    # Create the service
    service = ActuatorLLMService(db)
    
    # Show all actuators
    print("Current actuators in the system:")
    actuators = service.get_all_actuators()
    for actuator in actuators:
        print(f"- {actuator.name}: {'ON' if actuator.state else 'OFF'}")
    print("\n")
    
    # Demonstrate some LLM interactions
    demo_messages = [
        "What actuators do we have in the system?",
        "Is the irrigation pump turned on right now?",
        "Turn on the irrigation pump",
        "What's the status of all actuators?",
        "Turn off the greenhouse fan",
        "Can you pause monitoring for the water valve?",
        "Create a new light actuator for the greenhouse"
    ]
    
    for i, message in enumerate(demo_messages):
        print(f"\n[User Message {i+1}]: {message}")
        print("-" * 50)
        response = service.process_user_request(message)
        print(f"[Assistant Response]: \n{response}")
        print("=" * 80)
        
        # Wait a bit between requests
        time.sleep(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Actuator LLM Service Demo")
    parser.add_argument("--api-key", help="OpenAI API Key")
    args = parser.parse_args()
    
    # Use API key from args or environment
    api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Warning: No API key provided. Set OPENAI_API_KEY environment variable.")
    
    # Set up the database and run the demo
    engine, db = setup_demo_database()
    
    try:
        run_demo(db)
    finally:
        # Clean up
        db.close()
        # Optionally remove the database file if it's not needed
        # if os.path.exists("actuator_demo.db"):
        #     os.remove("actuator_demo.db")