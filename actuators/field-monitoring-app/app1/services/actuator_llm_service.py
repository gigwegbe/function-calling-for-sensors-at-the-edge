from sqlalchemy.orm import Session
from typing import Dict, List, Any, TypedDict, Optional
from datetime import datetime
import threading
import os
from dotenv import load_dotenv

# Import your existing models and utils
from app.models.actuator import Actuator
from app.models.sensor import Sensor
from app.utils.thingsboard import get_jwt_token, get_device_token, send_telemetry,create_or_update_device_on_thingsboard

# Import LangGraph components
from langgraph.graph import StateGraph, START,END
from langchain_community.chat_models import ChatOpenAI
from langchain.tools import Tool
from langchain.prompts import ChatPromptTemplate
from langchain.schema import SystemMessage, HumanMessage

load_dotenv()

class ActuatorControlState(TypedDict):
    """State representation for the LangGraph workflow."""
    messages: List[Dict[str, str]]
    actuator_states: Dict[str, Dict[str, Any]]
    sensor_values: Dict[str, Dict[str, Any]]
    user_request: str
    recommended_action: Optional[str]
    action_result: Optional[Dict[str, Any]]
    error: Optional[str]


class ActuatorLLMService:
    """Service that combines actuator control with LLM-powered interactions."""
    
    def __init__(self, db: Session, api_key: str = None):
        self.db = db
        self.api_key = api_key or os.environ.get("OPENAI_PROJECT_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
            
        self.llm = ChatOpenAI(api_key=self.api_key, temperature=0.2)
        self.actuator_graph = self._build_graph()
        
        # Similar to your original service
        self.monitoring_lock = threading.Lock()
        self.paused_actuators = {}  # Dictionary to track paused actuators

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine for actuator control."""
        workflow = StateGraph(ActuatorControlState)
        
        # Define the nodes
        workflow.add_node("analyze_request", self._analyze_request)
        workflow.add_node("fetch_context", self._fetch_context)
        workflow.add_node("execute_action", self._execute_action)
        workflow.add_node("format_response", self._format_response)
        
        # Define the edges
        workflow.add_edge(START, "analyze_request")  # Use the constant START instead of "START"
        workflow.add_edge("analyze_request", "fetch_context")
        workflow.add_edge("fetch_context", "execute_action")
        workflow.add_edge("execute_action", "format_response")
        workflow.add_edge("format_response", END)
        
        # Compile the graph
        return workflow.compile()

    def _analyze_request(self, state: ActuatorControlState) -> ActuatorControlState:
        """Use LLM to understand user request and determine intent."""
        # Basic system prompt that explains the available actuator operations
        system_prompt = """
        You are an intelligent assistant for an IoT actuator control system. 
        Your role is to interpret user requests related to actuators and recommend appropriate actions.
        
        Available operations:
        - Get information about actuators (status, type, sensors)
        - Turn actuators on or off
        - Create new actuators
        - Update actuator settings
        - Delete actuators
        - Pause or resume monitoring for actuators
        - Subscribe actuators to sensors
        
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

    def _fetch_context(self, state: ActuatorControlState) -> ActuatorControlState:
        """Fetch relevant context about actuators based on the user request."""
        # Get all actuators for context
        
        all_actuators = self.get_all_actuators()
        
        # Convert actuators to a format suitable for the state
        actuator_states = {}
        for actuator in all_actuators:
            actuator_states[actuator.id] = {
                "id": actuator.id,
                "name": actuator.name,
                "type": actuator.type,
                "state": actuator.state,
                "monitoring_active": actuator.monitoring_active,
                "last_state_change": actuator.last_state_change.isoformat() if actuator.last_state_change else None
            }
        
        state["actuator_states"] = actuator_states
        
        # Optionally fetch sensor data for context if needed
        # This could be expanded based on the specific request
        return state

    def _execute_action(self, state: ActuatorControlState) -> ActuatorControlState:
        """Execute the recommended action based on LLM analysis."""
        recommended_action = state["recommended_action"]
        actuator_states = state["actuator_states"]
        
        # Use another LLM call to determine specific parameters for the action
        execute_prompt = f"""
        Based on the user request: "{state['user_request']}" 
        
        You previously recommended this action: "{recommended_action}"
        
        Current actuator states:
        {actuator_states}
        
        Please specify exactly what action to take in JSON format with these fields:
        - action_type: One of ["get_info", "turn_on", "turn_off", "create", "update", "delete", "pause", "resume", "subscribe"]
        - actuator_id: ID of the actuator (if applicable)
        - parameters: Any additional parameters needed (as a dictionary)
        
        For 'create' actions, include these parameters: name, type, location
        For 'update' actions, include the fields to update and their new values
        
        Respond ONLY with valid JSON.
        """
        
        response = self.llm.invoke([HumanMessage(content=execute_prompt)])
        
        try:
            import json
            # Parse the JSON response
            action_data = json.loads(response.content)
            action_type = action_data.get("action_type", "get_info").lower()
            actuator_id = action_data.get("actuator_id")
            parameters = action_data.get("parameters", {})
            
            # Handle different action types
            if action_type == "turn_on":
                if actuator_id:
                    result = self.override_actuator_state(actuator_id, True)
                    state["action_result"] = {"action": "turn_on", "actuator_id": actuator_id, "success": result}
                else:
                    state["error"] = "No actuator ID provided for turn_on action"
                    
            elif action_type == "turn_off":
                if actuator_id:
                    result = self.override_actuator_state(actuator_id, False)
                    state["action_result"] = {"action": "turn_off", "actuator_id": actuator_id, "success": result}
                else:
                    state["error"] = "No actuator ID provided for turn_off action"
                    
            elif action_type == "create":
                # Extract creation parameters
                actuator_data = {
                    "name": parameters.get("name", "New Actuator"),
                    "type": parameters.get("type", "generic"),
                    "location": parameters.get("location", "unknown")
                }
                try:
                    new_actuator = self.create_actuator(actuator_data)
                    state["action_result"] = {
                        "action": "create", 
                        "actuator_id": new_actuator.id,
                        "actuator_name": new_actuator.name,
                        "success": True
                    }
                except Exception as e:
                    state["error"] = f"Failed to create actuator: {str(e)}"
                    
            elif action_type == "update":
                if actuator_id:
                    # Get update parameters
                    update_data = {k: v for k, v in parameters.items() if k != "actuator_id"}
                    try:
                        updated_actuator = self.update_actuator(actuator_id, update_data)
                        if updated_actuator:
                            state["action_result"] = {
                                "action": "update", 
                                "actuator_id": actuator_id,
                                "updated_fields": list(update_data.keys()),
                                "success": True
                            }
                        else:
                            state["error"] = f"Actuator with ID {actuator_id} not found"
                    except Exception as e:
                        state["error"] = f"Failed to update actuator: {str(e)}"
                else:
                    state["error"] = "No actuator ID provided for update action"
                    
            elif action_type == "delete":
                if actuator_id:
                    result = self.delete_actuator(actuator_id)
                    state["action_result"] = {"action": "delete", "actuator_id": actuator_id, "success": result}
                else:
                    state["error"] = "No actuator ID provided for delete action"
                    
            elif action_type == "pause":
                if actuator_id:
                    self.pause_actuator(actuator_id)
                    state["action_result"] = {"action": "pause", "actuator_id": actuator_id, "success": True}
                else:
                    state["error"] = "No actuator ID provided for pause action"
                    
            elif action_type == "resume":
                if actuator_id:
                    self.resume_actuator(actuator_id)
                    state["action_result"] = {"action": "resume", "actuator_id": actuator_id, "success": True}
                else:
                    state["error"] = "No actuator ID provided for resume action"
                    
            elif action_type == "subscribe":
                # This would link an actuator to sensors
                # Implementation would depend on your sensor subscription logic
                state["action_result"] = {"action": "subscribe", "message": "Sensor subscription not implemented yet"}
                
            else:  # get_info is the default action
                state["action_result"] = {"action": "get_info", "data": actuator_states}
                
        except json.JSONDecodeError:
            state["error"] = "Failed to parse action as JSON"
        except Exception as e:
            state["error"] = f"Error executing action: {str(e)}"
            
        return state

    def _format_response(self, state: ActuatorControlState) -> ActuatorControlState:
        """Format the final response to return to the user."""
        # Use the LLM to generate a helpful, natural language response
        format_prompt = f"""
        User request: "{state['user_request']}"
        
        Action taken: {state.get('action_result', {})}
        
        Current actuator states: {state['actuator_states']}
        
        Error (if any): {state.get('error', 'None')}
        
        Please provide a helpful, conversational response to the user that explains what was done
        and the current state of their actuators. Keep it friendly and informative.
        """
        
        response = self.llm.invoke([HumanMessage(content=format_prompt)])
        
        # Update the messages list with the assistant's response
        state["messages"].append({"role": "assistant", "content": response.content})
        return state

    def process_user_request(self, user_message: str) -> str:
        """Process a user request and return a response."""
        # Initialize the state
        initial_state = ActuatorControlState(
            messages=[{"role": "user", "content": user_message}],
            actuator_states={},
            sensor_values={},
            user_request=user_message,
            recommended_action=None,
            action_result=None,
            error=None
        )
        
        # Execute the workflow
        try:
            final_state = self.actuator_graph.invoke(initial_state)
            return final_state["messages"][-1]["content"]
        except Exception as e:
            return f"Sorry, I encountered an error processing your request: {str(e)}"

    # Include all your original ActuatorService methods below
    # Reusing your existing code
    
    def get_actuator(self, actuator_id: str) -> Actuator:
        """Retrieve an actuator by its ID."""
        return self.db.query(Actuator).filter(Actuator.id == actuator_id).first()
    
    def create_actuator(self, actuator_data: dict) -> Actuator:
        """Create a new actuator both locally and on ThingsBoard."""
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
        actuator_data["monitoring_active"] = False
        actuator_data["state"] = False
        actuator_data["last_state_change"] = datetime.utcnow()
        actuator_data["last_monitoring_change"] = datetime.utcnow()

        # Create the actuator locally
        actuator = Actuator(**actuator_data)
        self.db.add(actuator)
        self.db.commit()
        self.db.refresh(actuator)
        return actuator
    
    def update_actuator(self, actuator_id: str, updated_data: dict) -> Optional[Actuator]:
        """Update an existing actuator with new data."""
        actuator = self.get_actuator(actuator_id)
        if not actuator:
            return None

        # Update fields only if they are present in the updated_data
        for key, value in updated_data.items():
            if hasattr(actuator, key):
                setattr(actuator, key, value)

        # Update timestamps if specific fields are modified
        if "state" in updated_data and updated_data["state"] != actuator.state:
            actuator.last_state_change = datetime.utcnow()
        if "monitoring_active" in updated_data and updated_data["monitoring_active"] != actuator.monitoring_active:
            actuator.last_monitoring_change = datetime.utcnow()

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
    
    def override_actuator_state(self, actuator_id: str, state: bool) -> bool:
        """Override the state of an actuator."""
        actuator = self.get_actuator(actuator_id)
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
