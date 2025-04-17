from typing import Dict, List, Optional, Any, Tuple
from pydantic import BaseModel, Field
import os
import json
import re
import datetime
from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langchain.schema import SystemMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langchain.prompts import ChatPromptTemplate

from models.models import get_session_factory, init_db
from services.farm_control_service import FarmControlService

load_dotenv()  # Load environment variables

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime) or isinstance(obj, datetime.date):
            return obj.isoformat()
        return super(DateTimeEncoder, self).default(obj)
    
class FarmChatState(BaseModel):
    """State for the farm control chat interface."""
    messages: List[Dict] = Field(default_factory=list)
    user_request: Optional[str] = None
    intent: Optional[Dict] = None
    scenario: Optional[str] = None
    context: Optional[Dict] = None
    plan: Optional[List[Dict]] = None
    execution_results: Optional[List[Dict]] = None
    impact_analysis: Optional[Dict] = None
    response: Optional[str] = None
    clarification_needed: bool = False
    clarification_question: Optional[str] = None
    confirmation_needed: bool = False
    confirmation_details: Optional[Dict] = None
    debug_logs: List[str] = Field(default_factory=list)
    error_occurred: bool = False
    error_message: Optional[str] = None
    max_iterations: int = 10  # Add a counter to prevent infinite loops
    current_iteration: int = 0  # Track current iteration

# Define function schema for the farm control service
FUNCTION_DESCRIPTIONS = {
    "get_all_farms": {
        "description": "Get information about all farms in the system",
        "args": {"include_related": "Boolean to include related entities like fields, sensors, actuators"}
    },
    "get_farm_by_id": {
        "description": "Get information about a specific farm by ID",
        "args": {"farm_id": "ID of the farm", "include_related": "Boolean to include related entities"}
    },
    "get_all_fields": {
        "description": "Get information about all fields across all farms",
        "args": {"include_related": "Boolean to include related entities like sensors, actuators"}
    },
    "get_field_by_id": {
        "description": "Get information about a specific field by ID",
        "args": {"field_id": "ID of the field", "include_related": "Boolean to include related entities"}
    },
    "get_field_by_name": {
        "description": "Get information about a specific field by name",
        "args": {"field_name": "Name of the field", "include_related": "Boolean to include related entities"}
    },
    "get_all_sensors": {
        "description": "Get information about all sensors in the system",
        "args": {"include_related": "Boolean to include related field information"}
    },
    "get_sensor_by_id": {
        "description": "Get information about a specific sensor by ID",
        "args": {"sensor_id": "ID of the sensor", "include_related": "Boolean to include related field information"}
    },
    "get_all_actuators": {
        "description": "Get information about all actuators in the system",
        "args": {"include_related": "Boolean to include related entities"}
    },
    "get_actuator_by_type": {
        "description": "Get information about actuators of a specific type",
        "args": {"actuator_type": "Type of actuator (e.g., 'water_valves', 'pump')", "include_related": "Boolean to include related entities"}
    },
    "get_actuator_by_id": {
        "description": "Get information about a specific actuator by ID",
        "args": {"actuator_id": "ID of the actuator", "include_related": "Boolean to include related entities"}
    },
    "get_all_resources": {
        "description": "Get information about all resources (water tanks, fertilizer tanks, etc.)",
        "args": {"include_related": "Boolean to include related entities"}
    },
    "get_resource_by_id": {
        "description": "Get information about a specific resource by ID",
        "args": {"resource_id": "ID of the resource", "include_related": "Boolean to include related entities"}
    },
    "get_actuators_by_field": {
        "description": "Get all actuators associated with a specific field by ID",
        "args": {"field_id": "ID of the field", "include_related": "Boolean to include related entities"}
    },
    "get_actuators_by_field_name": {
        "description": "Get all actuators associated with a specific field by name",
        "args": {"field_name": "Name of the field", "include_related": "Boolean to include related entities"}
    },
    "get_sensors_by_field": {
        "description": "Get all sensors in a specific field by ID",
        "args": {"field_id": "ID of the field", "include_related": "Boolean to include related entities"}
    },
    "get_active_actuators": {
        "description": "Get all actuators that are currently active (open status)",
        "args": {"include_related": "Boolean to include related entities"}
    },
    "get_inactive_actuators": {
        "description": "Get all actuators that are currently inactive (closed status)",
        "args": {"include_related": "Boolean to include related entities"}
    },
    "get_resource_levels": {
        "description": "Get current levels of all resources (water tanks, fertilizer tanks, etc.)",
        "args": {}
    },
    "update_actuator_status": {
        "description": "Update the status of an actuator (open/close)",
        "args": {"actuator_id": "ID of the actuator", "new_status": "New status ('open', 'close', 'changing state')"}
    },
    "get_resource_dependent_actuators": {
        "description": "Get all actuators that depend on a specific resource",
        "args": {"resource_id": "ID of the resource", "include_related": "Boolean to include related entities"}
    },
    "update_resource_level": {
        "description": "Update the current level of a resource",
        "args": {"resource_id": "ID of the resource", "new_level": "New level value"}
    }
}

class EnhancedFarmChatInterface:
    """
    Enhanced natural language chat interface for farm control system.
    Allows farmers to manage irrigation, monitoring, and farm equipment
    through conversational language with improved context awareness.
    """
    
    def __init__(self, farm_control_service: FarmControlService,
               model_name: str = "gpt-4o", temperature: float = 0.1,
               api_key: str = None, debug_mode: bool = True):
        """Initialize the chat interface."""
        
        self.debug_mode = debug_mode
        self.farm_control_service = farm_control_service
        self.api_key = api_key or os.environ.get("OPENAI_PROJECT_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
            
        self.llm = ChatOpenAI(api_key=self.api_key, model=model_name, temperature=temperature)
        
        # Build the graph
        self.graph = self._build_graph()
        
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine for the farm chat interface."""
        
        # Create the state graph
        graph = StateGraph(FarmChatState)
        
        # Define edges for the graph
        # From START to parse_intent
        graph.add_edge(START, "parse_intent")
        
        def check_max_iterations(state):
            state.current_iteration += 1
            if state.current_iteration >= state.max_iterations:
                state.error_occurred = True
                state.error_message = "Maximum number of processing iterations reached."
                return "error_occurred"
                return None
           
    
        # Add a check for maximum iterations in each node function
        graph.add_node("parse_intent", lambda state: check_max_iterations(state) or self._parse_user_intent(state))
        graph.add_node("gather_context", lambda state: check_max_iterations(state) or self._gather_context(state))
        graph.add_node("create_plan", lambda state: check_max_iterations(state) or self._create_action_plan(state))
        graph.add_node("execute_plan", lambda state: check_max_iterations(state) or self._execute_action_plan(state))
        graph.add_node("analyze_impact", lambda state: check_max_iterations(state) or self._analyze_impact(state))
        graph.add_node("generate_response", lambda state: check_max_iterations(state) or self._generate_response(state))
        graph.add_node("request_clarification", lambda state: check_max_iterations(state) or self._request_clarification(state))
        graph.add_node("request_confirmation", lambda state: check_max_iterations(state) or self._request_confirmation(state))
        graph.add_node("handle_error", lambda state: check_max_iterations(state) or self._handle_error(state))
        
        # From parse_intent to other nodes based on conditions
        graph.add_conditional_edges(
            "parse_intent",
            self._route_after_intent_parsing,
            {
                "clarification_needed": "request_clarification",
                "error_occurred": "handle_error",
                "proceed": "gather_context",
                "max_iterations_reached": "handle_error"  # New condition
            }
        )
        
        # From gather_context to other nodes
        graph.add_conditional_edges(
            "gather_context",
            self._route_after_context_gathering,
            {
                "error_occurred": "handle_error",
                "proceed": "create_plan",
                "max_iterations_reached": "handle_error"  # New condition
            }
        )
        
        # From create_plan to other nodes
        graph.add_conditional_edges(
            "create_plan",
            self._route_after_plan_creation,
            {
                "confirmation_needed": "request_confirmation",
                "error_occurred": "handle_error",
                "proceed": "execute_plan",
                "max_iterations_reached": "handle_error"  # New condition
            }
        )
        
        # From request_confirmation to other nodes
        graph.add_conditional_edges(
            "request_confirmation",
            self._route_after_confirmation_request,
            {
                "confirmed": "execute_plan",
                "rejected": "generate_response",
                "error_occurred": "handle_error",
                "max_iterations_reached": "handle_error"  # New condition
            }
        )
        
        # From request_clarification back to parse_intent
        graph.add_edge("request_clarification", "generate_response")  # Changed to go directly to response
        
        # From execute_plan to analyze_impact or handle_error
        graph.add_conditional_edges(
            "execute_plan",
            self._route_after_execution,
            {
                "error_occurred": "handle_error",
                "proceed": "analyze_impact",
                "max_iterations_reached": "handle_error"  # New condition
            }
        )
        
        # From analyze_impact to generate_response
        graph.add_edge("analyze_impact", "generate_response")
        
        # From handle_error to generate_response
        graph.add_edge("handle_error", "generate_response")
        
        # From generate_response to END
        graph.add_edge("generate_response", END)
        
        # Compile the graph
        return graph.compile()

    
    def _parse_user_intent(self, state: FarmChatState) -> FarmChatState:
        """Parse the user's intent from their request."""
        
        if self.debug_mode:
            state.debug_logs.append(f"Parsing intent from: {state.user_request}")
        
        # Create template for intent parsing
        intent_parsing_template = ChatPromptTemplate.from_messages([
            ("system", """
            You are an assistant for a smart farm management system. Your task is to analyze the user's message and identify:
            1. The primary intent of the request
            2. Any specific entities mentioned (fields, actuators, resources, etc.)
            3. The operation requested (get info, control actuators, check status, etc.)
            
            You have access to the following farm control functions:
            {function_descriptions}
            
            When analyzing requests, try to map them to these available functions.
            
            Return your analysis as a structured JSON with the following format:
            {{
                "intent_category": "information_request" | "control_operation" | "status_check" | "problem_report" | "other",
                "specific_intent": "<more specific description of the intent>",
                "entities": {{
                    "fields": ["field_name1", "field_name2", ...],
                    "actuators": ["actuator_type1", "actuator_type2", ...],
                    "resources": ["resource_name1", "resource_name2", ...],
                    "sensors": ["sensor_type1", "sensor_type2", ...]
                }},
                "operation": "<operation_requested>",
                "parameters": {{
                    "<param_name>": "<param_value>",
                    ...
                }},
                "recommended_functions": [
                    {{
                        "function_name": "<name of function to call>",
                        "args": {{
                            "<arg_name>": "<arg_value>",
                            ...
                        }},
                        "purpose": "<why this function is needed>"
                    }},
                    ...
                ],
                "is_clear": true | false,
                "missing_information": ["<info1>", "<info2>", ...] if applicable
            }}
            """),
            ("human", "{user_request}")
        ])
        
        # Use JsonOutputParser for structured output
        output_parser = JsonOutputParser()
        
        # Chain the prompt and model together
        intent_chain = intent_parsing_template | self.llm | output_parser
        
        try:
            # Format function descriptions for the prompt
            formatted_functions = json.dumps(FUNCTION_DESCRIPTIONS, indent=2)
            
            # Execute the chain
            intent_data = intent_chain.invoke({
                "user_request": state.user_request,
                "function_descriptions": formatted_functions
            })
            
            # Update the state with the parsed intent
            state.intent = intent_data
            
            # Check if clarification is needed
            if not intent_data.get("is_clear", True):
                state.clarification_needed = True
                missing_info = intent_data.get("missing_information", [])
                
                # Generate a clarification question
                clarification_prompt = ChatPromptTemplate.from_messages([
                    ("system", """
                    You're helping manage a farm system. The user's request needs clarification.
                    Create a friendly question asking specifically about these missing pieces of information:
                    {missing_info}
                    
                    Keep your question conversational and short. Don't explain that you need clarification,
                    just ask directly what you need to know to help them.
                    """),
                    ("human", "{user_request}")
                ])
                
                clarification_chain = clarification_prompt | self.llm
                clarification_response = clarification_chain.invoke({
                    "missing_info": ", ".join(missing_info),
                    "user_request": state.user_request
                })
                
                state.clarification_question = clarification_response.content
            
            if self.debug_mode:
                state.debug_logs.append("Intent parsed successfully")
                if "recommended_functions" in intent_data:
                    state.debug_logs.append(f"Recommended functions: {json.dumps(intent_data['recommended_functions'], indent=2)}")
                
        except Exception as e:
            # If intent parsing fails, create a basic response
            state.error_occurred = True
            state.error_message = f"Error parsing intent: {str(e)}"
            if self.debug_mode:
                state.debug_logs.append(f"Error in intent parsing: {str(e)}")
                
        return state
    
    def _request_clarification(self, state: FarmChatState) -> FarmChatState:
        """Handle the need for clarification by adding a question to the messages."""
    
        if self.debug_mode:
            state.debug_logs.append(f"Requesting clarification: {state.clarification_question}")
            
        # Add the clarification question to the messages list
        message = {
            "role": "assistant",
            "content": state.clarification_question
        }
        state.messages.append(message)
        
        # Set the response to be the clarification question
        # This ensures it's returned to the user
        state.response = state.clarification_question
        
        # Reset clarification flags after asking
        state.clarification_needed = False
        state.clarification_question = None
        
        return state
    
    def _request_confirmation(self, state: FarmChatState) -> FarmChatState:
        """Handle the need for confirmation by adding a confirmation request to the messages."""
        
        if self.debug_mode:
            state.debug_logs.append(f"Requesting confirmation: {state.confirmation_details}")
            
        # Create a confirmation message
        if state.confirmation_details and "confirmation_message" in state.confirmation_details:
            confirmation_text = state.confirmation_details["confirmation_message"]
        else:
            # Generate a generic confirmation message based on the plan
            plan_summary = state.confirmation_details.get("plan_summary", "perform these operations") if state.confirmation_details else "proceed with the requested actions"
            confirmation_text = f"I'm about to {plan_summary}. Would you like me to proceed?"
        
        # Add the confirmation request to the messages list
        message = {
            "role": "assistant",
            "content": confirmation_text
        }
        state.messages.append(message)
        
        return state
    
    def _handle_error(self, state: FarmChatState) -> FarmChatState:
        """Handle any errors that occurred during processing."""
        
        if self.debug_mode:
            state.debug_logs.append(f"Handling error: {state.error_message}")
            
        # Format a user-friendly error message
        error_template = ChatPromptTemplate.from_messages([
            ("system", """
            You are an assistant for a smart farm management system. An error has occurred while processing a user request.
            Create a friendly, helpful message explaining the error and suggesting alternative actions.
            
            Guidelines:
            1. Be honest about the error but don't provide technical details
            2. Suggest alternative approaches when possible
            3. Keep the message brief and clear
            4. Don't use technical jargon
            """),
            ("human", """
            User request: {user_request}
            Error message: {error_message}
            
            Please create a friendly error message.
            """)
        ])
        
        try:
            # Generate a friendly error message
            error_chain = error_template | self.llm
            error_message = error_chain.invoke({
                "user_request": state.user_request,
                "error_message": state.error_message
            })
            
            # Set the response to the error message
            state.response = error_message.content
            
        except Exception as e:
            # Fallback error message if even error handling fails
            state.response = "I'm sorry, I encountered an issue while processing your request. Please try again or contact support if the problem persists."
            if self.debug_mode:
                state.debug_logs.append(f"Error in error handling: {str(e)}")
                
        return state
    
    # Update all routing functions to check for max iterations
    def _route_after_intent_parsing(self, state: FarmChatState) -> str:
        """Determine the next step after intent parsing."""
        # Check for max iterations first
        state.current_iteration += 1
        if state.current_iteration >= state.max_iterations:
            state.error_occurred = True
            state.error_message = "Maximum number of processing iterations reached."
            return "error_occurred"
            
        if state.error_occurred:
            return "error_occurred"
        elif state.clarification_needed:
            return "clarification_needed"
        else:
            return "proceed"
    
    def _route_after_context_gathering(self, state: FarmChatState) -> str:
        """Determine the next step after context gathering."""
        if state.error_occurred:
            return "error_occurred"
        else:
            return "proceed"
    
    def _route_after_plan_creation(self, state: FarmChatState) -> str:
        """Determine the next step after plan creation."""
        if state.error_occurred:
            return "error_occurred"
        elif state.confirmation_needed:
            return "confirmation_needed"
        else:
            return "proceed"
    
    def _route_after_confirmation_request(self, state: FarmChatState) -> str:
        """
        Determine the next step after a confirmation request.
        This would typically be handled after receiving a user's response.
        """
        # This would need to parse the user's response to determine if they confirmed
        # For now, we'll assume confirmed based on the most recent message
        
        if state.error_occurred:
            return "error_occurred"
        
        latest_msg = state.messages[-1] if state.messages else None
        if latest_msg and latest_msg.get("role") == "user":
            content = latest_msg.get("content", "").lower()
            # Check for confirmation words
            if any(word in content for word in ["yes", "yeah", "sure", "confirm", "proceed", "go ahead", "ok", "okay"]):
                return "confirmed"
            else:
                return "rejected"
        
        # Default to rejected if we can't determine
        return "rejected"
    
    def _route_after_execution(self, state: FarmChatState) -> str:
        """Determine the next step after plan execution."""
        if state.error_occurred:
            return "error_occurred"
        else:
            return "proceed"
    
    # Main interface methods
    def process_message(self, user_message: str) -> Dict:
        """Process a message from the user and return a response."""
        
        # Initialize the state
        state = FarmChatState(
            messages=[{"role": "user", "content": user_message}],
            user_request=user_message,
            debug_logs=[] if self.debug_mode else None
        )
        
        # Execute the graph
        final_state = self.graph.invoke(state)
        
        # Format the result
        result = {
            "response": final_state.response,
            "messages": final_state.messages + [{"role": "assistant", "content": final_state.response}]
        }
        
        # Include debug logs if enabled
        if self.debug_mode and final_state.debug_logs:
            result["debug_logs"] = final_state.debug_logs
            
        return result
    
    
    
    def _gather_context(self, state: FarmChatState) -> FarmChatState:
        """Gather relevant context based on the user's intent."""
    
        if self.debug_mode:
            state.debug_logs.append(f"Gathering context for intent: {state.intent}")
        
        try:
            context = {}
            intent_data = state.intent
            
            # Extract entity information from intent
            entities = intent_data.get("entities", {})
            fields = entities.get("fields", [])
            actuators = entities.get("actuators", [])
            resources = entities.get("resources", [])
            sensors = entities.get("sensors", [])
            
            # Determine the appropriate scenario based on intent category
            intent_category = intent_data.get("intent_category", "")
            specific_intent = intent_data.get("specific_intent", "")
            
            state.scenario = self._determine_scenario(intent_category, specific_intent)
            
            # Gather information about fields if mentioned
            if fields:
                field_info = []
                for field_name in fields:
                    try:
                        # Get field information by name
                        field_data = self.farm_control_service.get_field_by_name(field_name, include_related=True)
                        if field_data:
                            field_info.append(field_data)
                    except Exception as e:
                        if self.debug_mode:
                            state.debug_logs.append(f"Error getting field information for {field_name}: {str(e)}")
                
                context["fields"] = field_info
            else:
                # If no specific fields mentioned but fields context needed, get all fields
                if intent_category in ["information_request", "status_check"] and not any([actuators, resources, sensors]):
                    try:
                        context["fields"] = self.farm_control_service.get_all_fields(include_related=True)
                    except Exception as e:
                        if self.debug_mode:
                            state.debug_logs.append(f"Error getting all fields: {str(e)}")
            
            # Gather information about actuators if mentioned
            if actuators:
                actuator_info = []
                for actuator_type in actuators:
                    try:
                        # Get actuators by type
                        actuator_data = self.farm_control_service.get_actuator_by_type(actuator_type, include_related=True)
                        if actuator_data:
                            actuator_info.append(actuator_data)
                    except Exception as e:
                        if self.debug_mode:
                            state.debug_logs.append(f"Error getting actuator information for {actuator_type}: {str(e)}")
                
                context["actuators"] = actuator_info
            
            # Gather information about resources if mentioned
            if resources:
                resource_info = []
                for resource_name in resources:
                    # This is a placeholder - we would need a get_resource_by_name function
                    # For now, we'll get all resources and filter
                    try:
                        all_resources = self.farm_control_service.get_all_resources(include_related=True)
                        for resource in all_resources:
                            if resource.get("name", "").lower() == resource_name.lower():
                                resource_info.append(resource)
                                break
                    except Exception as e:
                        if self.debug_mode:
                            state.debug_logs.append(f"Error getting resource information for {resource_name}: {str(e)}")
                
                context["resources"] = resource_info
            elif intent_category in ["control_operation"] or "irrigation" in specific_intent.lower():
                # For irrigation and control operations, we need resource levels
                try:
                    context["resource_levels"] = self.farm_control_service.get_resource_levels()
                except Exception as e:
                    if self.debug_mode:
                        state.debug_logs.append(f"Error getting resource levels: {str(e)}")
            
            # Gather information about sensors if mentioned
            if sensors:
                sensor_info = []
                for sensor_type in sensors:
                    # This is a placeholder - we would need a get_sensor_by_type function
                    # For now, we'll just add it to the context to show we need to implement this
                    sensor_info.append({"sensor_type": sensor_type, "message": "Sensor information retrieval not implemented"})
                
                context["sensors"] = sensor_info
            
            # For specific field operations, gather all related actuators and sensors
            if fields and (intent_category in ["control_operation", "status_check"]):
                for field_name in fields:
                    try:
                        field_actuators = self.farm_control_service.get_actuators_by_field_name(field_name, include_related=True)
                        if field_actuators:
                            context.setdefault("field_actuators", {})[field_name] = field_actuators
                    except Exception as e:
                        if self.debug_mode:
                            state.debug_logs.append(f"Error getting actuators for field {field_name}: {str(e)}")
                    
                    try:
                        # Assuming there's a get_sensors_by_field_name method or similar
                        field_id = None
                        # First get the field ID from name
                        field_data = self.farm_control_service.get_field_by_name(field_name)
                        if field_data and "id" in field_data:
                            field_id = field_data["id"]
                            field_sensors = self.farm_control_service.get_sensors_by_field(field_id, include_related=True)
                            if field_sensors:
                                context.setdefault("field_sensors", {})[field_name] = field_sensors
                    except Exception as e:
                        if self.debug_mode:
                            state.debug_logs.append(f"Error getting sensors for field {field_name}: {str(e)}")
            
            # Update the state with the gathered context
            state.context = context
            
        except Exception as e:
            state.error_occurred = True
            state.error_message = f"Error gathering context: {str(e)}"
            if self.debug_mode:
                state.debug_logs.append(f"Error in context gathering: {str(e)}")
        
        return state

    def _determine_scenario(self, intent_category: str, specific_intent: str) -> str:
        """Determine the scenario based on intent category and specific intent."""
        
        # Map intents to scenarios
        if intent_category == "information_request":
            if "overview" in specific_intent.lower() or "status" in specific_intent.lower():
                return "system_overview"
            elif "field" in specific_intent.lower():
                return "field_information"
            elif "resource" in specific_intent.lower():
                return "resource_information"
            else:
                return "general_information"
        
        elif intent_category == "control_operation":
            if "irrigat" in specific_intent.lower() or "water" in specific_intent.lower():
                return "irrigation_control"
            elif "fertili" in specific_intent.lower():
                return "fertilization_control"
            elif "actuator" in specific_intent.lower() or "open" in specific_intent.lower() or "close" in specific_intent.lower():
                return "actuator_control"
            else:
                return "general_control"
        
        elif intent_category == "status_check":
            if "sensor" in specific_intent.lower():
                return "sensor_status"
            elif "actuator" in specific_intent.lower():
                return "actuator_status"
            elif "resource" in specific_intent.lower():
                return "resource_status"
            else:
                return "general_status"
        
        elif intent_category == "problem_report":
            return "problem_handling"
        
        else:
            return "general_assistance"

    def _create_action_plan(self, state: FarmChatState) -> FarmChatState:
        """Create an action plan based on the user's intent and gathered context."""
        
        if self.debug_mode:
            state.debug_logs.append(f"Creating action plan for scenario: {state.scenario}")
        
        try:
            # Initialize plan and confirmation flags
            plan = []
            confirmation_needed = False
            confirmation_details = {}
            
            # Get intent and context
            intent = state.intent
            context = state.context
            scenario = state.scenario
            
            # Check if we need to create a plan
            if intent.get("intent_category") in ["information_request", "status_check"]:
                # For information requests, we just need to gather data
                if scenario == "system_overview":
                    plan.append({
                        "action": "get_all_farms",
                        "args": {"include_related": True},
                        "purpose": "Get overview of all farms"
                    })
                    
                    plan.append({
                        "action": "get_all_fields",
                        "args": {"include_related": True},
                        "purpose": "Get overview of all fields"
                    })
                    
                    plan.append({
                        "action": "get_resource_levels",
                        "args": {},
                        "purpose": "Get current resource levels"
                    })
                    
                    plan.append({
                        "action": "get_active_actuators",
                        "args": {"include_related": True},
                        "purpose": "Get currently active actuators"
                    })
                
                elif scenario == "field_information":
                    # Check if specific fields were mentioned
                    fields = intent.get("entities", {}).get("fields", [])
                    
                    if fields:
                        for field_name in fields:
                            plan.append({
                                "action": "get_field_by_name",
                                "args": {"field_name": field_name, "include_related": True},
                                "purpose": f"Get information about field {field_name}"
                            })
                            
                            plan.append({
                                "action": "get_actuators_by_field_name",
                                "args": {"field_name": field_name, "include_related": True},
                                "purpose": f"Get actuators in field {field_name}"
                            })
                    else:
                        # No specific fields mentioned, get all
                        plan.append({
                            "action": "get_all_fields",
                            "args": {"include_related": True},
                            "purpose": "Get information about all fields"
                        })
                
                elif scenario == "resource_information":
                    plan.append({
                        "action": "get_all_resources",
                        "args": {"include_related": True},
                        "purpose": "Get information about all resources"
                    })
                    
                    plan.append({
                        "action": "get_resource_levels",
                        "args": {},
                        "purpose": "Get current resource levels"
                    })
                
                elif scenario == "actuator_status":
                    # Check if specific actuator types were mentioned
                    actuators = intent.get("entities", {}).get("actuators", [])
                    
                    if actuators:
                        for actuator_type in actuators:
                            plan.append({
                                "action": "get_actuator_by_type",
                                "args": {"actuator_type": actuator_type, "include_related": True},
                                "purpose": f"Get status of {actuator_type} actuators"
                            })
                    else:
                        # No specific actuator types mentioned, get all
                        plan.append({
                            "action": "get_all_actuators",
                            "args": {"include_related": True},
                            "purpose": "Get status of all actuators"
                        })
                
                elif scenario == "sensor_status":
                    # Get all sensors or sensors for specific fields
                    fields = intent.get("entities", {}).get("fields", [])
                    
                    if fields:
                        # For each field, get its sensors
                        for field_name in fields:
                            # First get field ID from name
                            field_plan = {
                                "action": "get_field_by_name",
                                "args": {"field_name": field_name},
                                "purpose": f"Get field ID for {field_name}"
                            }
                            plan.append(field_plan)
                            
                            # Then get sensors for that field
                            # This requires us to extract the field ID from the previous action's result
                            # We'll handle this in the execution phase
                            sensor_plan = {
                                "action": "get_sensors_by_field",
                                "args": {"field_id": "FIELD_ID_PLACEHOLDER", "include_related": True},
                                "purpose": f"Get sensors in field {field_name}",
                                "depends_on": field_plan
                            }
                            plan.append(sensor_plan)
                    else:
                        # No specific fields mentioned, get all sensors
                        plan.append({
                            "action": "get_all_sensors",
                            "args": {"include_related": True},
                            "purpose": "Get status of all sensors"
                        })
            
            elif intent.get("intent_category") == "control_operation":
                # For control operations, we need to update actuator statuses
                if scenario == "irrigation_control":
                    # Handle irrigation control
                    fields = intent.get("entities", {}).get("fields", [])
                    operation = intent.get("operation", "").lower()
                    
                    if fields:
                        for field_name in fields:
                            # Check if field actuators are already in context
                            field_actuators = context.get("field_actuators", {}).get(field_name, [])
                            
                            if not field_actuators:
                                # If not in context, add action to get them
                                plan.append({
                                    "action": "get_actuators_by_field_name",
                                    "args": {"field_name": field_name, "include_related": True},
                                    "purpose": f"Get irrigation actuators for field {field_name}"
                                })
                            
                            # Determine the new status based on operation
                            new_status = "open" if operation in ["start", "open", "turn on"] else "close"
                            
                            # Create placeholder for actuator control actions
                            # These will be populated during execution when we know the actuator IDs
                            plan.append({
                                "action": "update_actuator_status",
                                "args": {"actuator_id": "ACTUATOR_ID_PLACEHOLDER", "new_status": new_status},
                                "purpose": f"{new_status.capitalize()} irrigation for field {field_name}",
                                "is_placeholder": True,
                                "field_name": field_name,
                                "actuator_type": "water_valves"  # Assuming water_valves is the type for irrigation
                            })
                        
                        # Add check for resource levels
                        plan.append({
                            "action": "get_resource_levels",
                            "args": {},
                            "purpose": "Check water resource levels before irrigation"
                        })
                        
                        # This is a control operation, so we need confirmation
                        confirmation_needed = True
                        confirmation_details = {
                            "plan_summary": f"{'start' if new_status == 'open' else 'stop'} irrigation for field(s): {', '.join(fields)}",
                            "confirmation_message": f"I'll {'open' if new_status == 'open' else 'close'} the irrigation valves for {', '.join(fields)}. The water level will be checked before proceeding. Would you like me to continue?"
                        }
                    else:
                        # No fields specified, this is an error
                        state.error_occurred = True
                        state.error_message = "No fields specified for irrigation control"
                
                elif scenario == "actuator_control":
                    # Direct actuator control
                    actuators = intent.get("entities", {}).get("actuators", [])
                    operation = intent.get("operation", "").lower()
                    
                    # Determine the new status based on operation
                    new_status = "open" if operation in ["start", "open", "turn on"] else "close"
                    
                    if actuators:
                        for actuator_type in actuators:
                            # Add action to get actuators of this type
                            plan.append({
                                "action": "get_actuator_by_type",
                                "args": {"actuator_type": actuator_type, "include_related": True},
                                "purpose": f"Get {actuator_type} actuators"
                            })
                            
                            # Create placeholder for actuator control actions
                            plan.append({
                                "action": "update_actuator_status",
                                "args": {"actuator_id": "ACTUATOR_ID_PLACEHOLDER", "new_status": new_status},
                                "purpose": f"{new_status.capitalize()} {actuator_type} actuators",
                                "is_placeholder": True,
                                "actuator_type": actuator_type
                            })
                        
                        # This is a control operation, so we need confirmation
                        confirmation_needed = True
                        confirmation_details = {
                            "plan_summary": f"{'open' if new_status == 'open' else 'close'} the following actuators: {', '.join(actuators)}",
                            "confirmation_message": f"I'll {new_status} the {', '.join(actuators)}. Would you like me to proceed?"
                        }
                    else:
                        # No actuators specified, this is an error
                        state.error_occurred = True
                        state.error_message = "No actuators specified for control operation"
            
            # Update the state with the plan
            state.plan = plan
            state.confirmation_needed = confirmation_needed
            state.confirmation_details = confirmation_details
            
        except Exception as e:
            state.error_occurred = True
            state.error_message = f"Error creating action plan: {str(e)}"
            if self.debug_mode:
                state.debug_logs.append(f"Error in action plan creation: {str(e)}")
        
        return state

    def _execute_action_plan(self, state: FarmChatState) -> FarmChatState:
        """Execute the action plan and collect results."""
        
        if self.debug_mode:
            state.debug_logs.append(f"Executing action plan with {len(state.plan)} steps")
        
        try:
            # Initialize execution results
            execution_results = []
            
            # Track field IDs and actuator IDs for dependency resolution
            field_id_map = {}
            actuator_lists = {}
            
            # Execute each action in the plan
            for i, action in enumerate(state.plan):
                action_name = action.get("action")
                args = action.get("args", {})
                purpose = action.get("purpose", "")
                
                if self.debug_mode:
                    state.debug_logs.append(f"Executing action {i+1}: {action_name} - {purpose}")
                
                # Skip placeholder actions (they will be replaced with real actions)
                if action.get("is_placeholder", False):
                    continue
                
                # Check for dependencies
                if "depends_on" in action:
                    depends_on = action["depends_on"]
                    # If this is a sensor action depending on a field ID
                    if action_name == "get_sensors_by_field" and "field_id" in args:
                        field_name = None
                        for result in execution_results:
                            if result.get("action") == depends_on.get("action") and result.get("purpose") == depends_on.get("purpose"):
                                # Extract field ID from the result
                                field_data = result.get("result")
                                if field_data and "id" in field_data:
                                    args["field_id"] = field_data["id"]
                                    # Extract field name for logging
                                    field_name = field_data.get("name", "unknown")
                                break
                        
                        if "field_id" not in args or args["field_id"] == "FIELD_ID_PLACEHOLDER":
                            if self.debug_mode:
                                state.debug_logs.append(f"Could not resolve field ID dependency for {purpose}")
                            continue
                        
                        if self.debug_mode:
                            state.debug_logs.append(f"Resolved field ID for {field_name}: {args['field_id']}")
                
                # Execute the action by calling the appropriate method on farm_control_service
                if hasattr(self.farm_control_service, action_name):
                    method = getattr(self.farm_control_service, action_name)
                    result = method(**args)
                    
                    # Store the result
                    execution_result = {
                        "action": action_name,
                        "args": args,
                        "purpose": purpose,
                        "result": result
                    }
                    execution_results.append(execution_result)
                    
                    # Handle special cases for dependent actions
                    if action_name == "get_field_by_name":
                        # Store field ID for later use
                        if result and "id" in result:
                            field_id_map[args.get("field_name")] = result["id"]
                    
                    elif action_name == "get_actuators_by_field_name":
                        # Store actuators for later use
                        field_name = args.get("field_name")
                        if result:
                            actuator_lists[field_name] = result
                    
                    elif action_name == "get_actuator_by_type":
                        # Store actuators for later use
                        actuator_type = args.get("actuator_type")
                        if result:
                            actuator_lists[actuator_type] = result
                else:
                    if self.debug_mode:
                        state.debug_logs.append(f"Method {action_name} not found in farm_control_service")
            
            # Now handle placeholder actions by creating real actions based on the results
            additional_results = []
            
            for action in state.plan:
                if action.get("is_placeholder", False):
                    action_name = action.get("action")
                    args = action.get("args", {}).copy()  # Create a copy to modify
                    purpose = action.get("purpose", "")
                    
                    if action_name == "update_actuator_status":
                        # This is an actuator control placeholder
                        if "field_name" in action:
                            # This is for controlling actuators in a specific field
                            field_name = action["field_name"]
                            actuator_type = action.get("actuator_type")
                            
                            # Get the actuators for this field
                            field_actuators = actuator_lists.get(field_name, [])
                            
                            # Filter by actuator type if specified
                            if actuator_type and field_actuators:
                                field_actuators = [a for a in field_actuators if a.get("type") == actuator_type]
                            
                            if field_actuators:
                                for actuator in field_actuators:
                                    if "id" in actuator:
                                        # Create a new action for each actuator
                                        actuator_id = actuator["id"]
                                        args["actuator_id"] = actuator_id
                                        
                                        # Execute the action
                                        if hasattr(self.farm_control_service, action_name):
                                            method = getattr(self.farm_control_service, action_name)
                                            result = method(**args)
                                            
                                            # Store the result
                                            execution_result = {
                                                "action": action_name,
                                                "args": args.copy(),  # Create a copy as we'll modify args
                                                "purpose": f"{purpose} (Actuator ID: {actuator_id})",
                                                "result": result
                                            }
                                            additional_results.append(execution_result)
                        elif "actuator_type" in action:
                            # This is for controlling actuators of a specific type
                            actuator_type = action["actuator_type"]
                            
                            # Get the actuators of this type
                            type_actuators = actuator_lists.get(actuator_type, [])
                            
                            if type_actuators:
                                for actuator in type_actuators:
                                    if "id" in actuator:
                                        # Create a new action for each actuator
                                        actuator_id = actuator["id"]
                                        args["actuator_id"] = actuator_id
                                        
                                        # Execute the action
                                        if hasattr(self.farm_control_service, action_name):
                                            method = getattr(self.farm_control_service, action_name)
                                            result = method(**args)
                                            
                                            # Store the result
                                            execution_result = {
                                                "action": action_name,
                                                "args": args.copy(),  # Create a copy as we'll modify args
                                                "purpose": f"{purpose} (Actuator ID: {actuator_id})",
                                                "result": result
                                            }
                                            additional_results.append(execution_result)
            
            # Add the additional results to the execution results
            execution_results.extend(additional_results)
            
            # Update the state with the execution results
            state.execution_results = execution_results
            
        except Exception as e:
            state.error_occurred = True
            state.error_message = f"Error executing action plan: {str(e)}"
            if self.debug_mode:
                state.debug_logs.append(f"Error in action plan execution: {str(e)}")
        
        return state

    def _analyze_impact(self, state: FarmChatState) -> FarmChatState:
        """Analyze the impact of the executed actions."""
        
        if self.debug_mode:
            state.debug_logs.append("Analyzing impact of executed actions")
        
        try:
            # Initialize impact analysis structure
            impact = {
                "summary": "",
                "details": {},
                "status_changes": [],
                "resource_impacts": [],
                "recommendations": []
            }
            
            # Get execution results
            execution_results = state.execution_results or []
            
            # Track status changes for actuators
            actuator_status_changes = []
            
            # Track resource level changes
            resource_levels_before = None
            resource_levels_after = None
            
            # Group results by action type for easier analysis
            action_results = {}
            for result in execution_results:
                action = result.get("action")
                action_results.setdefault(action, []).append(result)
            
            # Check if resource levels were retrieved multiple times
            resource_level_results = action_results.get("get_resource_levels", [])
            if len(resource_level_results) >= 2:
                resource_levels_before = resource_level_results[0].get("result")
                resource_levels_after = resource_level_results[-1].get("result")
            
            # Check for actuator status updates
            actuator_updates = action_results.get("update_actuator_status", [])
            if actuator_updates:
                for update in actuator_updates:
                    args = update.get("args", {})
                    result = update.get("result")
                    
                    if result and "success" in result and result["success"]:
                        actuator_status_changes.append({
                            "actuator_id": args.get("actuator_id"),
                            "new_status": args.get("new_status"),
                            "purpose": update.get("purpose", "")
                        })
            
            # Build impact summary
            if actuator_status_changes:
                # Count actuators by status
                open_count = sum(1 for change in actuator_status_changes if change["new_status"] == "open")
                closed_count = sum(1 for change in actuator_status_changes if change["new_status"] == "close")
                
                status_summary = []
                if open_count > 0:
                    status_summary.append(f"Opened {open_count} actuator{'s' if open_count > 1 else ''}")
                if closed_count > 0:
                    status_summary.append(f"Closed {closed_count} actuator{'s' if closed_count > 1 else ''}")
                
                impact["summary"] = f"Actions completed: {', '.join(status_summary)}"
                impact["status_changes"] = actuator_status_changes
            else:
                # Information retrieval only
                impact["summary"] = "Retrieved information from the farm system"
            
            # Analyze resource impacts
            if resource_levels_before and resource_levels_after:
                resource_impacts = []
                
                # Compare before and after levels
                for resource_id, after_level in resource_levels_after.items():
                    if resource_id in resource_levels_before:
                        before_level = resource_levels_before[resource_id]
                        if before_level != after_level:
                            # Calculate the change
                            change = after_level - before_level
                            percent_change = (change / before_level) * 100 if before_level > 0 else 0
                            
                            resource_impacts.append({
                                "resource_id": resource_id,
                                "before": before_level,
                                "after": after_level,
                                "change": change,
                                "percent_change": percent_change
                            })
                
                impact["resource_impacts"] = resource_impacts
            
            # Generate recommendations based on actions and results
            recommendations = []
            
            # Check for low resource levels
            if resource_levels_after:
                for resource_id, level in resource_levels_after.items():
                    # Assuming 20% is a low threshold
                    if level < 20:
                        recommendations.append({
                            "type": "resource_warning",
                            "message": f"Resource ID {resource_id} is at {level}% capacity. Consider refilling soon."
                        })
            
            # Add recommendations based on actuator changes
            if actuator_status_changes:
                # If we opened irrigation valves, recommend checking after some time
                if any(change["new_status"] == "open" for change in actuator_status_changes):
                    recommendations.append({
                        "type": "follow_up",
                        "message": "Irrigation has been started. Consider checking field moisture levels in a few hours."
                    })
            
            impact["recommendations"] = recommendations
            
            # Update the state with the impact analysis
            state.impact_analysis = impact
            
        except Exception as e:
            state.error_occurred = True
            state.error_message = f"Error analyzing impact: {str(e)}"
            if self.debug_mode:
                state.debug_logs.append(f"Error in impact analysis: {str(e)}")
        
        return state
    

    def _generate_response(self, state: FarmChatState) -> FarmChatState:
        """Generate a human-friendly response based on the execution results and impact analysis."""
        
        if self.debug_mode:
            state.debug_logs.append("Generating response")
        
        try:
            # Prepare data for response generation
            response_data = {
                "user_request": state.user_request,
                "intent": state.intent,
                "scenario": state.scenario,
                "execution_results": state.execution_results,
                "impact_analysis": state.impact_analysis,
                "error_occurred": state.error_occurred,
                "error_message": state.error_message
            }
            
            # Create template for response generation
            response_template = ChatPromptTemplate.from_messages([
                ("system", """
                You are an assistant for a smart farm management system. Your task is to generate a natural, conversational response to the user based on the data provided.
                
                Guidelines:
                1. Use natural, friendly language suitable for farmers and farm managers
                2. Focus on the most relevant information first
                3. If actions were taken, clearly explain what was done and the impact
                4. Include any relevant recommendations or warnings
                5. Don't use technical jargon unless necessary
                6. Keep responses concise but complete
                
                Data about the request and results:
                {response_data}
                """),
                ("human", "Generate a response for: {user_request}")
            ])
            
            # Chain the prompt and model together
            response_chain = response_template | self.llm
            
            # Execute the chain
            response = response_chain.invoke({
                "response_data": json.dumps(response_data, cls=DateTimeEncoder),
                "user_request": state.user_request
            })
            
            # Update the state with the generated response
            state.response = response.content
            
            # Add the response to messages
            message = {
                "role": "assistant",
                "content": state.response
            }
            state.messages.append(message)
            
        except Exception as e:
            # If response generation fails, create a basic response
            state.response = f"I understand your request about the farm, but I encountered an error processing it. Please try again or rephrase your question."
            if self.debug_mode:
                state.debug_logs.append(f"Error in response generation: {str(e)}")
                
            # Add the basic response to messages
            message = {
                "role": "assistant",
                "content": state.response
            }
            state.messages.append(message)
        
        return state
    
    
    def chat(self, messages: List[Dict]) -> Dict:
        """
        Process a conversation with message history and return a response.
        Useful for maintaining context over multiple turns.
        """
        if not messages or not isinstance(messages, list):
            return {"error": "Invalid message format. Expected a list of message dictionaries."}
        
        # Get the latest user message
        latest_user_message = next((msg for msg in reversed(messages) if msg.get("role") == "user"), None)
        
        if not latest_user_message:
            return {"error": "No user message found in conversation history."}
        
        # Initialize the state
        state = FarmChatState(
            messages=messages.copy(),  # Make a copy to avoid modifying the original
            user_request=latest_user_message.get("content", ""),
            debug_logs=[] if self.debug_mode else None
        )
        
        # Execute the graph with safety mechanisms
        try:
            final_state = self.graph.invoke(state)
            
            # Extract the response from the final state
            response = ""
            if isinstance(final_state, dict):
                response = final_state.get("response", "")
            else:
                response = getattr(final_state, "response", "")
            
            # If response is empty despite completing execution, generate a fallback response
            if not response:
                response = "I processed your request but was unable to generate a proper response. Could you please try again with more details?"
                
        except Exception as e:
            # Handle any exceptions from the graph execution
            response = "I encountered an error while processing your request. Please try again with a different query."
            if self.debug_mode:
                state.debug_logs.append(f"Graph execution error: {str(e)}")
        
        # Add the response to messages list (if not already there)
        if response and (not messages or messages[-1].get("role") != "assistant" or messages[-1].get("content") != response):
            updated_messages = messages + [{"role": "assistant", "content": response}]
        else:
            updated_messages = messages.copy()
        
        # Format the result
        result = {
            "response": response,
            "messages": updated_messages
        }
        
        # Include debug logs ONLY if debug_mode is True
        if self.debug_mode and state.debug_logs and len(state.debug_logs) > 0:
            result["debug_logs"] = state.debug_logs
                
        return result
        
# Application initialization code
def initialize_farm_chat_interface(api_key=None, model_name="gpt-4o", debug_mode=False):
    """Initialize the farm chat interface with the necessary components."""
    # Get a session factory
    engine = init_db()
    session_factory = get_session_factory(engine=engine)
    
    # Initialize the farm control service
    farm_control_service = FarmControlService(session_factory)
    
    # Initialize the chat interface
    chat_interface = EnhancedFarmChatInterface(
        farm_control_service=farm_control_service,
        model_name=model_name,
        api_key=api_key,
        debug_mode=debug_mode
    )
    
    return chat_interface


def run_demo(debug_mode=True):
    """Run a demo of the farm chat interface."""
    
    # Get the API key
    api_key = os.environ.get("OPENAI_PROJECT_API_KEY")
    
    # Initialize the chat interface
    chat_interface = initialize_farm_chat_interface(api_key=api_key, debug_mode=debug_mode)
    
    # Welcome message
    print("=== Smart Farm Management Chat Interface ===")
    print("Type 'exit' to quit the demo\n")
    
    # Start conversation
    messages = []
    
    while True:
        # Get user input
        user_input = input("\nYou: ")
        
        # Check for exit command
        if user_input.lower() in ["exit", "quit"]:
            print("\nThank you for using the Smart Farm Management Chat Interface!")
            break
        
        # Add user message to history
        messages.append({"role": "user", "content": user_input})
        
        # Process the message
        response = chat_interface.chat(messages)
        
        # Print the assistant's response
        print(f"\nFarm Assistant: {response['response']}")
        
        # Update messages
        messages = response["messages"]
        
        # Print debug logs only if debug mode is enabled and logs exist
        if debug_mode and "debug_logs" in response and response["debug_logs"]:
            print("\n--- Debug Logs ---")
            for log in response["debug_logs"]:
                print(f"  {log}")
            print("------------------\n")

# Example usage
if __name__ == "__main__":
    # Set debug_mode=False to disable debug logs
    run_demo(debug_mode=True)  # Change to False to disable debug logs