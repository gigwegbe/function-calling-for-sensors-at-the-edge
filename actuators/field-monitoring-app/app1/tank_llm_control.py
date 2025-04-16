import logging
from sqlalchemy.orm import Session
from fastapi import FastAPI, Depends, HTTPException, Body
from typing import List, Dict, Any, Optional
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from app.utils.db import get_db
from app.services.tank_farm_actuator_service import TankFarmActuatorLLMService
from app.models.all_models import Actuator  # Import the Actuator model

# Configure logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Tank Farm & Actuator Control API",
    description="API for managing irrigation, tanks, pumps, valves, and monitoring resources",
    version="2.0.0"
)

# CORS Middleware (optional, configure as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this to restrict origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Models
class Message(BaseModel):
    content: str

class ConversationResponse(BaseModel):
    response: str
    actuator_states: Optional[Dict[str, Any]] = None
    resource_states: Optional[Dict[str, Any]] = None

class ActuatorCreate(BaseModel):
    name: str
    type: str
    location: Optional[str] = None
    flow_rate: Optional[float] = None
    power_consumption: Optional[float] = None
    additionalInfo: dict = {}

# Dependency to initialize the service
def get_tank_farm_service(db: Session = Depends(get_db)) -> TankFarmActuatorLLMService:
    return TankFarmActuatorLLMService(db)

# Chat endpoint
@app.post("/chat", response_model=ConversationResponse)
async def chat_with_tank_farm_system(
    message: Message = Body(...),
    service: TankFarmActuatorLLMService = Depends(get_tank_farm_service)
):
    """Chat interface for natural language control of the tank farm and actuators."""
    logger.debug("Received chat request: %s", message.content)
    try:
        response = service.process_user_request(message.content)
        logger.debug("LLM response: %s", response)
        
        # Fetch actuator and resource states
        actuator_states = {
            actuator.id: {
                "id": actuator.id,
                "name": actuator.name,
                "type": actuator.type,
                "state": actuator.state,
                "monitoring_active": actuator.monitoring_active
            }
            for actuator in service.db.query(Actuator).all()
        }
        resource_states = service.tank_monitor.get_tank_data()
        
        return ConversationResponse(
            response=response,
            actuator_states=actuator_states,
            resource_states=resource_states
        )
    except Exception as e:
        logger.error("Error processing chat request: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")

# Actuator endpoints
@app.get("/actuators", response_model=List[Dict[str, Any]])
async def get_actuators(service: TankFarmActuatorLLMService = Depends(get_tank_farm_service)):
    """Get all actuators."""
    actuators = service.db.query(service.Actuator).all()
    return [
        {
            "id": a.id,
            "name": a.name,
            "type": a.type,
            "state": a.state,
            "monitoring_active": a.monitoring_active,
            "location": a.location,
            "flow_rate": a.flow_rate,
            "power_consumption": a.power_consumption
        }
        for a in actuators
    ]

@app.post("/actuators", response_model=Dict[str, Any])
async def create_actuator(
    actuator_data: ActuatorCreate = Body(...),
    service: TankFarmActuatorLLMService = Depends(get_tank_farm_service)
):
    """Create a new actuator."""
    try:
        actuator = service.Actuator(
            id=f"{actuator_data.type}_{int(time.time())}",
            name=actuator_data.name,
            type=actuator_data.type,
            location=actuator_data.location or "Default",
            flow_rate=actuator_data.flow_rate or 0.0,
            power_consumption=actuator_data.power_consumption or 0.0,
            state=False,
            monitoring_active=True
        )
        service.db.add(actuator)
        service.db.commit()
        return {
            "id": actuator.id,
            "name": actuator.name,
            "type": actuator.type,
            "state": actuator.state,
            "monitoring_active": actuator.monitoring_active,
            "location": actuator.location,
            "flow_rate": actuator.flow_rate
        }
    except Exception as e:
        logger.error("Failed to create actuator: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create actuator: {str(e)}")

@app.put("/actuators/{actuator_id}/state", response_model=Dict[str, Any])
async def update_actuator_state(
    actuator_id: str,
    state: bool = Body(..., embed=True),
    service: TankFarmActuatorLLMService = Depends(get_tank_farm_service)
):
    """Update the state of an actuator."""
    actuator = service.db.query(service.Actuator).filter(service.Actuator.id == actuator_id).first()
    if not actuator:
        raise HTTPException(status_code=404, detail="Actuator not found")
    actuator.state = state
    actuator.last_state_change = datetime.utcnow()
    service.db.commit()
    return {
        "id": actuator.id,
        "name": actuator.name,
        "state": actuator.state,
        "updated_at": actuator.last_state_change
    }

# Tank resource endpoints
@app.get("/resources", response_model=Dict[str, Any])
async def get_resources(service: TankFarmActuatorLLMService = Depends(get_tank_farm_service)):
    """Get all tank resources."""
    return {"resources": service.tank_monitor.get_tank_data()}

# Irrigation endpoints
@app.get("/irrigation/status", response_model=Dict[str, Any])
async def get_irrigation_status(service: TankFarmActuatorLLMService = Depends(get_tank_farm_service)):
    """Get status of active irrigation sessions."""
    return {
        "active_sessions": len(service.irrigation_controller.active_sessions),
        "sessions": service.irrigation_controller.active_sessions
    }

@app.post("/irrigation/start", response_model=Dict[str, Any])
async def start_irrigation(
    pump_id: str = Body(...),
    valve_ids: List[str] = Body(...),
    tank_id: str = Body(...),
    service: TankFarmActuatorLLMService = Depends(get_tank_farm_service)
):
    """Start a new irrigation session."""
    return service.irrigation_controller.start_irrigation(pump_id, valve_ids, tank_id)

@app.post("/irrigation/stop/{session_id}", response_model=Dict[str, Any])
async def stop_irrigation(
    session_id: str,
    service: TankFarmActuatorLLMService = Depends(get_tank_farm_service)
):
    """Stop an active irrigation session."""
    return service.irrigation_controller.stop_irrigation(session_id)

# Recommendations and statistics
@app.get("/recommendations", response_model=List[Dict[str, Any]])
async def get_recommendations(service: TankFarmActuatorLLMService = Depends(get_tank_farm_service)):
    """Get system recommendations."""
    return service.irrigation_controller.get_pending_recommendations()

@app.get("/statistics/water-usage", response_model=Dict[str, Any])
async def get_water_usage_stats(
    days: int = 7,
    service: TankFarmActuatorLLMService = Depends(get_tank_farm_service)
):
    """Get water usage statistics."""
    return service.irrigation_controller.get_water_usage_stats(days)