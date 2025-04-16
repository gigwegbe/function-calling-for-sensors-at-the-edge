from fastapi import FastAPI, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Union
from models import init_db, get_session_factory
from farm_control_service import FarmControlService
from farm_chat_interface import EnhancedFarmChatInterface, create_farm_chat_interface
import traceback

# Initialize database
engine = init_db()
SessionFactory = get_session_factory(engine)

# Create service
farm_service = FarmControlService(SessionFactory)

# Use the enhanced farm chat interface
farm_chat = create_farm_chat_interface(farm_service, model_name="gpt-4o")

app = FastAPI(title="Farm Control System API")

# Pydantic models for request/response
class StatusUpdate(BaseModel):
    status: str

class ResourceUpdate(BaseModel):
    level: str

class ScheduleData(BaseModel):
    start_time: str
    duration: int
    days: List[str]
    actuators: List[str]

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str
    metadata: Dict = Field(default_factory=dict)


# Routes
@app.get("/")
def read_root():
    return {"message": "Welcome to Farm Control System API"}

# Farm routes
@app.get("/farms", response_model=List[Dict])
def get_farms():
    return farm_service.get_all_farms()

@app.get("/farms/{farm_id}", response_model=Dict)
def get_farm(farm_id: str):
    farm = farm_service.get_farm_by_id(farm_id)
    if not farm:
        raise HTTPException(status_code=404, detail=f"Farm {farm_id} not found")
    return farm

# Field routes
@app.get("/fields", response_model=List[Dict])
def get_fields():
    return farm_service.get_all_fields()

@app.get("/fields/{field_id}", response_model=Dict)
def get_field(field_id: str):
    field = farm_service.get_field_by_id(field_id)
    if not field:
        raise HTTPException(status_code=404, detail=f"Field {field_id} not found")
    return field

@app.get("/fields/name/{field_name}", response_model=Dict)
def get_field_by_name(field_name: str):
    field = farm_service.get_field_by_name(field_name)
    if not field:
        raise HTTPException(status_code=404, detail=f"Field {field_name} not found")
    return field

@app.get("/fields/{field_id}/actuators", response_model=List[Dict])
def get_field_actuators(field_id: str):
    actuators = farm_service.get_actuators_by_field(field_id)
    if actuators is None:
        raise HTTPException(status_code=404, detail=f"Field {field_id} not found")
    return actuators

# Actuator routes
@app.get("/actuators", response_model=List[Dict])
def get_actuators():
    return farm_service.get_all_actuators()

@app.get("/actuators/active", response_model=List[Dict])
def get_active_actuators():
    return farm_service.get_active_actuators()

@app.get("/actuators/inactive", response_model=List[Dict])
def get_inactive_actuators():
    return farm_service.get_inactive_actuators()

@app.get("/actuators/{actuator_id}", response_model=Dict)
def get_actuator(actuator_id: str):
    actuator = farm_service.get_actuator_by_id(actuator_id)
    if not actuator:
        raise HTTPException(status_code=404, detail=f"Actuator {actuator_id} not found")
    return actuator

@app.get("/actuators/field/{field_id}", response_model=List[Dict])
def get_actuators_by_field(field_id: str):
    actuators = farm_service.get_actuators_by_field(field_id)
    if actuators is None:
        raise HTTPException(status_code=404, detail=f"Field {field_id} not found")
    return actuators

@app.get("/actuators/field_name/{field_name}", response_model=List[Dict])
def get_actuators_by_field_name(field_name: str):
    actuators = farm_service.get_actuators_by_field_name(field_name)
    if actuators is None:
        raise HTTPException(status_code=404, detail=f"Field {field_name} not found")
    return actuators


@app.get("/actuators/type/{actuator_type}", response_model=List[Dict])
def get_actuators_by_type(actuator_type: str):
    actuators = farm_service.get_actuator_by_type(actuator_type)
    if not actuators:
        raise HTTPException(status_code=404, detail=f"No actuators found of type {actuator_type}")
    return actuators

@app.put("/actuators/{actuator_id}/status", response_model=Dict)
def update_actuator_status(actuator_id: str, status_update: StatusUpdate):
    result = farm_service.update_actuator_status(actuator_id, status_update.status)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

# Resource routes
@app.get("/resources", response_model=List[Dict])
def get_resources():
    return farm_service.get_all_resources()

@app.get("/resources/levels", response_model=Dict)
def get_resource_levels():
    return farm_service.get_resource_levels()

@app.get("/resources/{resource_id}", response_model=Dict)
def get_resource(resource_id: str):
    resource = farm_service.get_resource_by_id(resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail=f"Resource {resource_id} not found")
    return resource

@app.get("/resources/{resource_id}/dependent-actuators", response_model=Union[List[Dict], Dict])
def get_resource_dependent_actuators(resource_id: str):
    result = farm_service.get_resource_dependent_actuators(resource_id)
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result

@app.put("/resources/{resource_id}/level", response_model=Dict)
def update_resource_level(resource_id: str, level_update: ResourceUpdate):
    result = farm_service.update_resource_level(resource_id, level_update.level)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result

# Scheduling routes
@app.post("/fields/{field_id}/schedule", response_model=Dict)
def create_irrigation_schedule(field_id: str, schedule_data: ScheduleData):
    field = farm_service.get_field_by_id(field_id)
    if not field:
        raise HTTPException(status_code=404, detail=f"Field {field_id} not found")
    
    return farm_service.create_irrigation_schedule(field_id, schedule_data.dict())

# Chat interface endpoint
@app.post("/chat", response_model=ChatResponse)
async def chat_with_farm_system(chat_request: ChatRequest):
    try:
        # Directly access the message attribute from the Pydantic model
        message = chat_request.message
        chat_result = farm_chat.chat(message)
        
        # Make sure we're accessing the response as a dictionary key
        response_text = chat_result.get("response", "No response generated")
        
        # Clean metadata to ensure it's JSON serializable
        metadata = {
            "intent": chat_result.get("intent"),
            "scenario": chat_result.get("scenario"),
            "plan": chat_result.get("plan"),
            # Filter out None values and ensure all objects are serializable
            "execution_results": [
                {k: v for k, v in result.items() if k != 'action'} 
                for result in (chat_result.get("execution_results") or [])
            ] if chat_result.get("execution_results") else None,
            "impact_analysis": chat_result.get("impact_analysis")
        }
        
        return ChatResponse(
            response=response_text,
            metadata=metadata
        )
    except Exception as e:
        print(f"Error in chat processing: {str(e)}")
        traceback.print_exc()  # Print full stack trace for debugging
        raise HTTPException(status_code=500, detail=f"Chat processing error: {str(e)}")
    
# Farm system overview endpoint
@app.get("/system/overview", response_model=Dict)
def get_system_overview():
    """Get a comprehensive overview of the farm system."""
    try:
        overview = farm_chat.get_system_overview()
        return overview
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting system overview: {str(e)}")

# Stateful chat sessions
chat_sessions = {}

@app.post("/chat/{session_id}", response_model=ChatResponse)
async def chat_with_session(session_id: str, chat_request: ChatRequest):
    """Endpoint for session-based chat to maintain conversation context."""
    try:
        # Create new session chat interface if this is a new session
        if session_id not in chat_sessions:
            chat_sessions[session_id] = create_farm_chat_interface(farm_service, model_name="gpt-4o")
            
        # Use the session-specific chat interface
        chat_result = chat_sessions[session_id].chat(chat_request.message)
        
        response_text = chat_result.get("response", "No response generated")
        
        # Clean metadata to ensure it's JSON serializable
        metadata = {
            "intent": chat_result.get("intent"),
            "scenario": chat_result.get("scenario"),
            "plan": chat_result.get("plan"),
            # Filter out None values and ensure all objects are serializable
            "execution_results": [
                {k: v for k, v in result.items() if k != 'action'} 
                for result in (chat_result.get("execution_results") or [])
            ] if chat_result.get("execution_results") else None,
            "impact_analysis": chat_result.get("impact_analysis")
        }
        
        return ChatResponse(
            response=response_text,
            metadata=metadata
        )
    except Exception as e:
        print(f"Error in session chat processing: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chat processing error: {str(e)}")

# Session management endpoints
@app.delete("/chat/{session_id}")
async def delete_chat_session(session_id: str):
    """Delete a chat session."""
    if session_id in chat_sessions:
        del chat_sessions[session_id]
        return {"message": f"Session {session_id} deleted successfully"}
    raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

@app.get("/chat/sessions", response_model=List[str])
async def list_chat_sessions():
    """List all active chat sessions."""
    return list(chat_sessions.keys())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8060)