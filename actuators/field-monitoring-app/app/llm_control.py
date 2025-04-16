import logging
from sqlalchemy.orm import Session
from fastapi import FastAPI, Depends, HTTPException, Body
from typing import List, Dict, Any, Optional
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.utils.db import get_db
from app.services.actuator_llm_service import ActuatorLLMService

# Configure logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Actuator Control LLM API",
    description="API for managing fields, devices, sensors, and actuators",
    version="1.0.0"
)

# CORS Middleware (optional, configure as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this to restrict origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Message(BaseModel):
    content: str

class ConversationResponse(BaseModel):
    response: str
    actuator_states: Optional[Dict[str, Any]] = None

@app.post("/chat", response_model=ConversationResponse)
async def chat_with_actuator_system(
    message: Message = Body(...),
    db: Session = Depends(get_db)
):
    """Chat interface for natural language control of actuators."""
    logger.debug("Received chat request: %s", message.content)
    try:
        service = ActuatorLLMService(db)
        response = service.process_user_request(message.content)
        logger.debug("LLM response: %s", response)
        
        # Get current actuator states for the response
        actuators = service.get_all_actuators()
        actuator_states = {}
        for actuator in actuators:
            actuator_states[actuator.id] = {
                "id": actuator.id,
                "name": actuator.name,
                "type": actuator.type,
                "state": actuator.state,
                "monitoring_active": actuator.monitoring_active
            }
        logger.debug("Actuator states: %s", actuator_states)
        
        return ConversationResponse(response=response, actuator_states=actuator_states)
    except Exception as e:
        logger.error("Error processing chat request: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")

# Standard CRUD endpoints
@app.get("/actuators", response_model=List[Dict[str, Any]])
async def get_actuators(db: Session = Depends(get_db)):
    """Get all actuators."""
    logger.debug("Fetching all actuators")
    service = ActuatorLLMService(db)
    actuators = service.get_all_actuators()
    logger.debug("Fetched actuators: %s", actuators)
    return [
        {
            "id": a.id,
            "name": a.name,
            "type": a.type,
            "state": a.state,
            "monitoring_active": a.monitoring_active,
            "last_state_change": a.last_state_change,
            "last_monitoring_change": a.last_monitoring_change
        }
        for a in actuators
    ]

@app.get("/actuators/{actuator_id}", response_model=Dict[str, Any])
async def get_actuator(actuator_id: str, db: Session = Depends(get_db)):
    """Get a specific actuator by ID."""
    logger.debug("Fetching actuator with ID: %s", actuator_id)
    service = ActuatorLLMService(db)
    actuator = service.get_actuator(actuator_id)
    if not actuator:
        logger.warning("Actuator not found: %s", actuator_id)
        raise HTTPException(status_code=404, detail="Actuator not found")
    
    logger.debug("Fetched actuator: %s", actuator)
    return {
            "id": actuator.id,
            "name": actuator.name,
            "type": actuator.type,
            "state": actuator.state,
            "monitoring_active": actuator.monitoring_active,
            "last_state_change": actuator.last_state_change,
            "last_monitoring_change": actuator.last_monitoring_change
    }

class ActuatorCreate(BaseModel):
    name: str
    type: str
    label: str
    additionalInfo: dict = {}

@app.post("/actuators", response_model=Dict[str, Any])
async def create_actuator(
    actuator_data: ActuatorCreate = Body(...),
    db: Session = Depends(get_db)
):
    """Create a new actuator."""
    logger.debug("Creating actuator with data: %s", actuator_data.dict())
    service = ActuatorLLMService(db)
    try:
        actuator = service.create_actuator(actuator_data.dict())
        logger.debug("Created actuator: %s", actuator)
        return {
            "id": actuator.id,
            "name": actuator.name,
            "type": actuator.type,
            "state": actuator.state,
            "monitoring_active": actuator.monitoring_active
        }
    except Exception as e:
        logger.error("Failed to create actuator: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create actuator: {str(e)}")

@app.put("/actuators/{actuator_id}/state", response_model=Dict[str, Any])
async def update_actuator_state(
    actuator_id: str,
    state: bool = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    """Override the state of an actuator."""
    logger.debug("Updating state for actuator ID: %s to %s", actuator_id, state)
    service = ActuatorLLMService(db)
    result = service.override_actuator_state(actuator_id, state)
    if not result:
        logger.warning("Failed to update actuator state for ID: %s", actuator_id)
        raise HTTPException(status_code=404, detail="Failed to update actuator state")
    
    actuator = service.get_actuator(actuator_id)
    logger.debug("Updated actuator: %s", actuator)
    return {
        "id": actuator.id,
        "name": actuator.name,
        "state": actuator.state,
        "updated_at": actuator.last_state_change
    }