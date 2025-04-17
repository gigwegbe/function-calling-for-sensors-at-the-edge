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
        "description": "Update the status of an actuator (open/close). Common commands include: 'open', 'start', 'activate', 'turn on', 'switch on', 'enable', 'power on' for opening; and 'close', 'stop', 'deactivate', 'turn off', 'switch off', 'disable', 'shut down', 'power off' for closing.",
        "args": {"actuator_id": "ID of the actuator", "new_status": "New status ('open', 'close')"}
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
        
        # Initialize system info
        self.system_info = {}
        self.status_cache = {
            "last_update": None,
            "active_actuators": None,
            "field_status": {},
            "resource_levels": None
        }
        self.conversation_memory = []
        self.recent_mentions = {
            "fields": [],
            "actuators": [],
            "resources": []
        }
        
        # Set cache lifetime (5 minutes)
        self.cache_lifetime = datetime.timedelta(minutes=5)
        # Prefetch available information about the farm system
        self._prefetch_system_info()
        self.system_context = self._create_system_context()
        self.pending_confirmation = None
        
        self.api_key = api_key or os.environ.get("OPENAI_PROJECT_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
            
        self.llm = ChatOpenAI(api_key=self.api_key, model=model_name, temperature=temperature)
        
        # Build the graph
        self.graph = self._build_graph()
    
    def _log(self, message):
        """Log debug information if debug mode is enabled."""
        if self.debug_mode:
            print(f"[DEBUG] {message}")
            
    def _prefetch_system_info(self):
        """Enhanced system info prefetch with resource mapping."""
        try:
            self.system_info = {
                "farms": self.farm_control_service.get_all_farms(),
                "fields": self.farm_control_service.get_all_fields(),
                "actuators": self.farm_control_service.get_all_actuators(),
                "sensors": self.farm_control_service.get_all_sensors(),
                "resources": self.farm_control_service.get_all_resources()
            }
            
            # Add field name mapping
            self.field_name_map = {}
            for field in self.system_info.get("fields", []):
                name = field.get("name", "").lower()
                if name:
                    self.field_name_map[name] = field.get("id")
                    if not name.endswith("field"):
                        self.field_name_map[f"{name} field"] = field.get("id")
            
            # Add actuator name mapping
            self.actuator_name_map = {}
            for actuator in self.system_info.get("actuators", []):
                name = actuator.get("name", "").lower()
                if name:
                    self.actuator_name_map[name] = actuator.get("id")
                    
            # Add resource name mapping
            self.resource_name_map = {}
            for resource in self.system_info.get("resources", []):
                name = resource.get("name", "").lower()
                if name:
                    self.resource_name_map[name] = resource.get("id")
                    
            # Add crop to field mapping
            self.field_crop_map = {}
            for field in self.system_info.get("fields", []):
                crop = field.get("crop", "").lower()
                if crop:
                    if crop not in self.field_crop_map:
                        self.field_crop_map[crop] = []
                    self.field_crop_map[crop].append(field.get("id"))
                    
            self._log(f"Prefetched system info with {len(self.system_info['farms'])} farms, "
                     f"{len(self.system_info['fields'])} fields, "
                     f"{len(self.system_info['sensors'])} sensors, "
                     f"{len(self.system_info['actuators'])} actuators, "
                     f"{len(self.system_info['resources'])} resources")
                     
        except Exception as e:
            self._log(f"Error prefetching system info: {str(e)}")
            self.system_info = {}
            
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
        graph.add_node("analyze_request", lambda state: check_max_iterations(state) or self._analyze_request(state))
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
        You are an assistant for a smart farm management system. You have access to the following:

        1. The primary intent of the request
        2. Any specific entities mentioned (fields, actuators, resources, etc.)
        3. The operation requested (get info, control actuators, check status, etc.)

        You have access to the following farm control functions:
        {function_descriptions}

        Detected Patterns in User Request:
        

        Common Command Patterns:
        - Irrigation: "irrigate", "water", "start irrigation"
        - Status Queries: "status", "state", "condition"
        - Resource Levels: "level", "volume", "capacity"
        - Control Operations: "open", "close", "start", "stop"
        - Bulk Operations: "all", "every", "each"
       

        Your task is to:
        1. Analyze the user's message and identified patterns
        2. Map the request to available functions and system components
        3. Identify any missing or ambiguous information
        4. Determine the most appropriate action plan

        Return your analysis as a structured JSON with the following format:
        {{
            "intent_category": "information_request" | "control_operation" | "status_check" | "problem_report" | "other",
            "specific_intent": "<detailed description of the intent>",
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
                    "purpose": "<why this function is needed>",
                    "priority": "high" | "medium" | "low"
                }},
                ...
            ],
            "is_clear": true | false,
            "missing_information": ["<info1>", "<info2>", ...],
            "detected_patterns": {{
                "has_irrigation_command": <boolean>,
                "is_status_query": <boolean>,
                "is_control_operation": <boolean>,
                "involves_multiple_components": <boolean>
            }}
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
    
    def _extract_field_reference(self, text: str) -> Tuple[str, str]:
        """
        Extracts field references from text and returns a tuple of (field_id, field_name).
        Returns (None, None) if no reference found.
        """
        text_lower = text.lower()
        
        # First check for exact field name matches
        for field in self.system_info.get("fields", []):
            field_name = field.get("name", "").lower()
            if field_name and field_name in text_lower:
                return field.get("id"), field.get("name")
        
        # Then check for cardinal directions
        cardinal_directions = ["north", "south", "east", "west", "northeast", 
                            "northwest", "southeast", "southwest", "central"]
        
        for direction in cardinal_directions:
            if direction in text_lower:
                for field in self.system_info.get("fields", []):
                    field_name = field.get("name", "").lower()
                    if direction in field_name:
                        return field.get("id"), field.get("name")
        
        # Try to match by field number ("field 3")
        field_num_match = re.search(r'field\s+(\d+)', text_lower)
        if field_num_match:
            number = int(field_num_match.group(1))
            # Assuming field IDs might be like "F001", "F002", etc.
            potential_id = f"F{number:03d}"
            
            for field in self.system_info.get("fields", []):
                if field.get("id") == potential_id:
                    return potential_id, field.get("name")
        
        # Add specific handling for "first field", "second field", etc.
        ordinal_match = re.search(r'(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth)\s+field', text_lower)
        if ordinal_match:
            ordinal_words = {"first": 0, "second": 1, "third": 2, "fourth": 3, 
                            "fifth": 4, "sixth": 5, "seventh": 6, "eighth": 7, "ninth": 8}
            index = ordinal_words.get(ordinal_match.group(1), 0)
            fields = self.system_info.get("fields", [])
            if 0 <= index < len(fields):
                return fields[index].get("id"), fields[index].get("name")
        
        # Add handling for recently mentioned fields in conversation
        if self.conversation_memory:
            for entry in reversed(self.conversation_memory):
                if "entities" in entry and "field" in entry["entities"]:
                    recent_field = entry["entities"]["field"]
                    self._log(f"Using recently mentioned field: {recent_field['name']}")
                    return recent_field["id"], recent_field["name"]
        
        return None, None
    
    def _extract_actuator_reference(self, text: str) -> Tuple[str, str]:
        """Extract actuator ID and name from text."""
        text_lower = text.lower()
        
        # Check for explicit actuator IDs with format like "FD-0900"
        actuator_id_match = re.search(r'([A-Z]+-\d{4})', text, re.IGNORECASE)
        if actuator_id_match:
            actuator_id = actuator_id_match.group(1)
            for actuator in self.system_info.get("actuators", []):
                if actuator.get("id") == actuator_id:
                    return actuator_id, actuator.get("name", "")
        
        # Check for actuator type references
        type_keywords = {
            "water valve": "water_valves",
            "pump": "pump",
            "fertilizer": "fertilizer_dispensers",
            "fertilizer dispenser": "fertilizer_dispensers",
            "dispenser": "fertilizer_dispensers"
        }
        
        for keyword, act_type in type_keywords.items():
            if keyword in text_lower:
                # Find actuators of this type
                matching_actuators = [a for a in self.system_info.get("actuators", []) 
                                    if a.get("type") == act_type]
                if matching_actuators:
                    # Return the first one or try to find one in the mentioned field
                    field_id, _ = self._extract_field_reference(text)
                    if field_id:
                        for actuator in matching_actuators:
                            if actuator.get("field_id") == field_id:
                                return actuator.get("id"), actuator.get("name", "")
                    
                    # If no field-specific match, return the first one
                    return matching_actuators[0].get("id"), matching_actuators[0].get("name", "")
        
        return None, None
    
    def _get_response_suggestions(self, scenario: str) -> List[str]:
        """Get contextual suggestions based on the current scenario."""
        suggestions = []
        
        if scenario == "irrigation_control":
            suggestions = [
                "Check moisture levels in the fields",
                "View water resource levels",
                "Stop irrigation in specific fields",
                "Create an irrigation schedule"
            ]
        elif scenario == "field_information":
            suggestions = [
                "What's planted in each field?",
                "Show me all fields and their crops",
                "How big is the north field?",
                "Check field irrigation status"
            ]
        elif scenario == "actuator_control":
            suggestions = [
                "Show me all active actuators",
                "Check valve status in specific fields",
                "Turn on/off specific equipment",
                "Get equipment status by type"
            ]
        elif scenario == "resource_management":
            suggestions = [
                "Check water tank levels",
                "View fertilizer storage status",
                "Monitor resource consumption",
                "Get alerts for low resources"
            ]
        elif scenario == "system_overview":
            suggestions = [
                "Show me active equipment",
                "Which fields are being irrigated?",
                "Check resource levels",
                "View system status"
            ]
        else:
            # Default suggestions
            suggestions = [
                "Check field conditions",
                "Monitor equipment status",
                "View resource levels",
                "Get system overview"
            ]
        
        return suggestions
    
    def _analyze_request(self, state: FarmChatState) -> FarmChatState:
        """
        Analyze the user request with enhanced contextual understanding and 
        reduced need for clarifications by leveraging historical context.
        """
        # Ensure user_request exists
        if not state.user_request or state.user_request.strip() == "":
            state.error_occurred = True
            state.error_message = "No user request provided"
            return state
            
        # Update status cache for fresh information
        self._update_status_cache()
            
        # Handle greetings and basic status requests with richer information
        greeting_pattern = r'^(hi|hello|hey|greetings|good morning|good afternoon|good evening|how are you|how\'s it going)\s*\??$'
        overview_pattern = r'^(tell me about|show me|what\'s|what is|show|overview|status of|report on) (my|the) (farm|fields?|situation|system|overview)\s*\??$'
        
        if re.match(greeting_pattern, state.user_request.strip().lower()):
            # Respond with greeting and comprehensive farm overview
            # Count active equipment by type for more informative response
            active_actuators = self.status_cache.get("active_actuators", [])
            active_by_type = {}
            for actuator in active_actuators:
                actuator_type = actuator.get("type", "unknown")
                if actuator_type not in active_by_type:
                    active_by_type[actuator_type] = 0
                active_by_type[actuator_type] += 1
            
            # Format active equipment summary
            active_summary = []
            for actuator_type, count in active_by_type.items():
                # Format the actuator type for display
                display_type = actuator_type.replace("_", " ")
                if display_type.endswith("s"):
                    display_type = display_type[:-1] + "(s)"
                active_summary.append(f"{count} {display_type}")
            
            # Count irrigating fields with names
            irrigating_fields = []
            for field_id, status in self.status_cache.get("field_status", {}).items():
                if status.get("is_irrigating", False):
                    # Find field name
                    for field in self.system_info.get("fields", []):
                        if field.get("id") == field_id:
                            irrigating_fields.append(field.get("name", "Unknown field"))
                            break
            
            # Check resource levels for insights
            resources = self.status_cache.get("resource_levels", {})
            low_resources = []
            for resource_id, resource_info in resources.items():
                try:
                    current = float(resource_info.get("current_level", "0").split()[0].replace(",", ""))
                    capacity = float(resource_info.get("capacity", "0").split()[0].replace(",", ""))
                    if capacity > 0 and (current / capacity) < 0.25:
                        low_resources.append(resource_info.get("name", "Unknown resource"))
                except (ValueError, IndexError):
                    continue
            
            # Build a more informative greeting
            greeting_response = f"Hello! Welcome to your Thousand Hills Farm management system. Here's your current status:\n\n"
            
            # Add active equipment summary
            if active_summary:
                greeting_response += f"**Active Equipment:** {', '.join(active_summary)}\n\n"
            else:
                greeting_response += "**Active Equipment:** No equipment currently active\n\n"
            
            # Add irrigation status
            if irrigating_fields:
                if len(irrigating_fields) == 1:
                    greeting_response += f"**Irrigation:** Currently watering {irrigating_fields[0]}\n\n"
                else:
                    greeting_response += f"**Irrigation:** Watering {len(irrigating_fields)} fields: {', '.join(irrigating_fields)}\n\n"
            else:
                greeting_response += "**Irrigation:** No fields currently being irrigated\n\n"
            
            # Add resource warnings if any
            if low_resources:
                if len(low_resources) == 1:
                    greeting_response += f"**❗ Notice:** {low_resources[0]} is running low\n\n"
                else:
                    greeting_response += f"**❗ Notice:** Low resources: {', '.join(low_resources)}\n\n"
            
            greeting_response += f"How can I help with your farm management today?"
            
            state.response = greeting_response
            return state
            
        elif re.match(overview_pattern, state.user_request.strip().lower()):
            # Provide a comprehensive system overview with actionable insights
            
            # Get current active actuators with improved grouping
            active_actuators = self.status_cache.get("active_actuators", [])
            active_by_type = {}
            for actuator in active_actuators:
                actuator_type = actuator.get("type", "unknown")
                field_id = actuator.get("field_id")
                
                # Group by type and field for more context
                if actuator_type not in active_by_type:
                    active_by_type[actuator_type] = {}
                
                field_name = "Unassigned"
                if field_id:
                    for field in self.system_info.get("fields", []):
                        if field.get("id") == field_id:
                            field_name = field.get("name", "Unknown field")
                            break
                
                if field_name not in active_by_type[actuator_type]:
                    active_by_type[actuator_type][field_name] = 0
                active_by_type[actuator_type][field_name] += 1
            
            # Get resource status with level percentage
            resources = self.status_cache.get("resource_levels", {})
            resource_summary = []
            for resource_id, resource_info in resources.items():
                name = resource_info.get("name", "Unknown")
                current = resource_info.get("current_level", "Unknown")
                capacity = resource_info.get("capacity", "Unknown")
                
                # Calculate percentage if possible
                percentage = ""
                try:
                    current_val = float(current.split()[0].replace(",", ""))
                    capacity_val = float(capacity.split()[0].replace(",", ""))
                    if capacity_val > 0:
                        percentage = f" ({(current_val / capacity_val) * 100:.0f}%)"
                except (ValueError, IndexError):
                    pass
                
                resource_summary.append({
                    "name": name,
                    "level": f"{current} / {capacity}{percentage}",
                    "is_low": percentage and int(percentage.strip("()%")) < 25
                })
            
            # Format field status with more details
            irrigating_fields = []
            fields_by_crop = {}
            
            for field in self.system_info.get("fields", []):
                field_id = field.get("id")
                field_name = field.get("name", "Unknown field")
                crop = field.get("crop", "Unknown crop")
                
                if crop not in fields_by_crop:
                    fields_by_crop[crop] = []
                fields_by_crop[crop].append(field_name)
                
                field_status = self.status_cache.get("field_status", {}).get(field_id, {})
                if field_status.get("is_irrigating", False):
                    irrigating_fields.append(field_name)
            
            # Build the comprehensive overview response
            overview_response = "# Thousand Hills Farm - System Overview\n\n"
            
            # Equipment section
            overview_response += "## Equipment Status\n"
            if active_actuators:
                for actuator_type, fields in active_by_type.items():
                    display_type = actuator_type.replace("_", " ").title()
                    overview_response += f"### {display_type}\n"
                    for field_name, count in fields.items():
                        overview_response += f"* {field_name}: {count} active\n"
            else:
                overview_response += "* No equipment currently active\n"
            
            # Field section
            overview_response += "\n## Field Status\n"
            if irrigating_fields:
                overview_response += "### Currently Irrigating\n"
                for field in irrigating_fields:
                    overview_response += f"* {field}\n"
            
            overview_response += "\n### Fields by Crop\n"
            for crop, fields in fields_by_crop.items():
                overview_response += f"* {crop}: {', '.join(fields)}\n"
            
            # Resource section
            overview_response += "\n## Resource Levels\n"
            for resource in resource_summary:
                prefix = "❗ " if resource["is_low"] else ""
                overview_response += f"* {prefix}{resource['name']}: {resource['level']}\n"
            
            # Add recommendations if applicable
            if any(resource["is_low"] for resource in resource_summary):
                overview_response += "\n## Recommendations\n"
                overview_response += "* Consider refilling low resources soon\n"
            
            if not irrigating_fields and len(self.system_info.get("fields", [])) > 0:
                overview_response += "* No fields are currently being irrigated. Use 'irrigate [field name]' to start watering\n"
            
            state.response = overview_response
            return state
    
        self._log(f"Analyzing request: {state.user_request}")
    
        try:
            # Enhanced intent extraction with better context usage
            # Expanded regex patterns for entity extraction
            patterns = {
                "actuator_ids": r"([A-Z]+-\d{4})",
                "field_ids": r"field\s+(\d+)|field\s+(\w+)",
                "field_names": r"([A-Za-z]+)\s+field|([A-Za-z]+ern)\s+field?|field\s+of\s+([A-Za-z]+)|([A-Za-z]+)\s+Field",  # Added capitalized Field
                "resource_ids": r"(RES-\d{4})",
                "open_command": r"\b(open|start|activate|turn\s+on|switch\s+on|enable|power\s+on)\b",
                "close_command": r"\b(close|stop|deactivate|turn\s+off|switch\s+off|disable|shut(\s+down)?|power\s+off)\b",
                "status_query": r"\b(status|state|condition|what\s+is|how\s+is)\b",
                "level_query": r"\b(level|volume|amount|capacity|how\s+much)\b",
                "all_keyword": r"\b(all|every|each)\b",
                "actuator_types": r"\b(valves?|pumps?|actuators?|water\s+valves?|sensors?|equipment|machines?|devices?)\b",
                "irrigation_command": r"\b(irrigate|water|start\s+irrigation|begin\s+watering)\b",
                "irrigation_stop": r"\b(stop\s+irrigation|stop\s+watering|end\s+irrigation)\b",
                "moisture_query": r"\b(moisture|wetness|humidity|soil\s+moisture)\b",
                "temperature_query": r"\b(temperature|heat|warmth|how\s+hot|how\s+cold)\b",
                "bulk_operation": r"\b(all|every|each|multiple|several|many)\b",
                "crop_reference": r"\b(corn|wheat|soy|soybeans|barley|alfalfa|cotton|rice|potatoes|vegetables)\b"
            }
    
            entities = {
                "actuator_ids": re.findall(patterns["actuator_ids"], state.user_request, re.IGNORECASE),
                "field_ids": [x[0] or x[1] for x in re.findall(patterns["field_ids"], state.user_request, re.IGNORECASE) if x[0] or x[1]],
                "field_names": [],  # We'll extract these more carefully below
                "resource_ids": re.findall(patterns["resource_ids"], state.user_request, re.IGNORECASE),
                "is_irrigation_command": bool(re.search(patterns["irrigation_command"], state.user_request, re.IGNORECASE)),
                "is_irrigation_stop": bool(re.search(patterns["irrigation_stop"], state.user_request, re.IGNORECASE)),
                "is_moisture_query": bool(re.search(patterns["moisture_query"], state.user_request, re.IGNORECASE)),
                "is_temperature_query": bool(re.search(patterns["temperature_query"], state.user_request, re.IGNORECASE)),
                "is_bulk_operation": bool(re.search(patterns["bulk_operation"], state.user_request, re.IGNORECASE))
            }
    
            # Signal flags to assist LLM
            regex_signals = {
                "has_all_keyword": bool(re.search(patterns["all_keyword"], state.user_request, re.IGNORECASE)),
                "has_open": bool(re.search(patterns["open_command"], state.user_request, re.IGNORECASE)),
                "has_close": bool(re.search(patterns["close_command"], state.user_request, re.IGNORECASE)),
                "is_status_query": bool(re.search(patterns["status_query"], state.user_request, re.IGNORECASE)),
                "is_level_query": bool(re.search(patterns["level_query"], state.user_request, re.IGNORECASE)),
            }
            
            # Enhanced actuator related patterns
            actuator_patterns = {
                "list_actuators": r"\b(what|list|show|get|tell).*(actuators?|equipment|devices?)\b",
                "available_actuators": r"\b(available|active|current|existing)\s*(actuators?|equipment|devices?)\b",
                "actuator_status": r"\b(status|state|condition)\s*(of|for)?\s*(actuators?|equipment|devices?)\b",
                # FIX: Added patterns for inactive actuators
                "inactive_actuators": r"\b(inactive|closed|off|disabled)\s*(actuators?|equipment|devices?)\b"
            }

            # More comprehensive field name extraction with priority given to exact matches
            # Extract field names from patterns
            field_name_matches = []
            
            # First check for explicit field name patterns
            for match in re.finditer(patterns["field_names"], state.user_request, re.IGNORECASE):
                groups = match.groups()
                for group in groups:
                    if group:
                        field_name_matches.append(group.lower())

            # Now check for exact field names in the text
            for field in self.system_info.get("fields", []):
                field_name = field.get("name", "").lower()
                if field_name and field_name in state.user_request.lower():
                    field_name_matches.append(field_name)
                    
                    # Also check without "field" suffix
                    if field_name.endswith(" field") and field_name[:-6] in state.user_request.lower():
                        field_name_matches.append(field_name[:-6])
            
            # Check for crop-based field references
            crop_matches = re.findall(patterns["crop_reference"], state.user_request, re.IGNORECASE)
            for crop in crop_matches:
                crop_lower = crop.lower()
                if crop_lower in self.field_crop_map:
                    # If we find fields with this crop type, add their names
                    for field_id in self.field_crop_map[crop_lower]:
                        for field in self.system_info.get("fields", []):
                            if field.get("id") == field_id:
                                field_name_matches.append(field.get("name", "").lower())
            
            # Look for cardinal directions as potential field names
            cardinal_directions = ["north", "south", "east", "west", "northeast", "northwest", "southeast", "southwest", "central"]
            for direction in cardinal_directions:
                if direction in state.user_request.lower():
                    # Check if this direction corresponds to a field
                    potential_field = f"{direction} field"
                    if potential_field in self.field_name_map:
                        field_name_matches.append(direction)
                    
                    # Also check for variations like "northern field"
                    directional_variations = [f"{direction}ern", f"{direction}ern field"]
                    for variation in directional_variations:
                        if variation in state.user_request.lower() and variation in self.field_name_map:
                            field_name_matches.append(variation)
            
            # Add recently mentioned fields for better context continuity
            if not field_name_matches and self.recent_mentions["fields"]:
                # Check if request implies continuing with the same field
                continuity_patterns = [
                    r"\b(there|it|that field|this field|the field|same field|this one)\b",
                    r"\b(check|status|moisture|temperature|irrigation)\b"
                ]
                
                has_continuity_marker = any(re.search(pattern, state.user_request, re.IGNORECASE) 
                                           for pattern in continuity_patterns)
                
                if has_continuity_marker:
                    field_name_matches.extend(self.recent_mentions["fields"])
            
            # Remove duplicates while preserving order
            entities["field_names"] = list(dict.fromkeys(field_name_matches))
            
            # Map field names to IDs for easier processing
            entities["field_name_to_id"] = {}
            for name in entities["field_names"]:
                clean_name = name.lower().strip()
                if clean_name in self.field_name_map:
                    entities["field_name_to_id"][clean_name] = self.field_name_map[clean_name]
                    
                    # Also check with "field" appended if not already present
                    if not clean_name.endswith("field"):
                        field_variant = f"{clean_name} field" 
                        if field_variant in self.field_name_map:
                            entities["field_name_to_id"][clean_name] = self.field_name_map[field_variant]
            
            # Extract actuator references with enhanced natural language understanding
            actuator_matches = []
            
            # First check for explicit actuator IDs
            actuator_matches.extend(entities["actuator_ids"])
            
            # Then check for natural language references to actuators
            for actuator_key in self.actuator_name_map:
                if actuator_key in state.user_request.lower():
                    actuator_matches.append(self.actuator_name_map[actuator_key])
            
            # Add recently mentioned actuators for continuity
            if not actuator_matches and self.recent_mentions["actuators"]:
                continuity_patterns = [
                    r"\b(it|that|this one|the equipment|the device|this device|same equipment)\b",
                    r"\b(status|open|close|turn on|turn off|activate|deactivate)\b"
                ]
                
                has_continuity_marker = any(re.search(pattern, state.user_request, re.IGNORECASE) 
                                           for pattern in continuity_patterns)
                
                if has_continuity_marker:
                    actuator_matches.extend(self.recent_mentions["actuators"])
            
            # Remove duplicates
            entities["actuator_ids"] = list(dict.fromkeys(actuator_matches))
            
            # Extract resource references
            resource_matches = []
            
            # First check for explicit resource IDs
            resource_matches.extend(entities["resource_ids"])
            
            # Then check for natural language references to resources
            for resource_key in self.resource_name_map:
                if resource_key in state.user_request.lower():
                    resource_matches.append(self.resource_name_map[resource_key])
            
            # Remove duplicates
            entities["resource_ids"] = list(dict.fromkeys(resource_matches))
            
            # Safely extract actuator type if present
            actuator_type_match = re.search(patterns["actuator_types"], state.user_request, re.IGNORECASE)
            regex_signals["actuator_type"] = actuator_type_match.group(0).lower() if actuator_type_match else None
            
            # Try to resolve field references
            if not entities["field_ids"] and not entities["field_names"]:
                field_id, field_name = self._extract_field_reference(state.user_request)
                if field_id:
                    entities["field_ids"] = [field_id]
                    entities["field_names"] = [field_name]

            # Try to resolve actuator references
            if not entities["actuator_ids"]:
                actuator_id, actuator_name = self._extract_actuator_reference(state.user_request)
                if actuator_id:
                    entities["actuator_ids"] = [actuator_id]
            
            
            # Include pre-fetched system information with richer context
            system_info_summary = {
                "field_count": len(self.system_info.get("fields", [])),
                "actuator_count": len(self.system_info.get("actuators", [])),
                "field_names": [field.get("name") for field in self.system_info.get("fields", [])],
                "actuator_types": list(set(actuator.get("type") for actuator in self.system_info.get("actuators", []))),
                "resource_types": list(set(resource.get("content") for resource in self.system_info.get("resources", []))),
                "active_fields": [
                    field.get("name") for field in self.system_info.get("fields", [])
                    if field.get("id") in self.status_cache.get("field_status", {}) and
                    self.status_cache["field_status"][field.get("id")].get("is_irrigating", False)
                ]
            }
            
            # Add conversation memory with improved context
            memory_context = ""
            if self.conversation_memory:
                last_exchanges = self.conversation_memory[-min(3, len(self.conversation_memory)):]
                memory_context = "Recent conversation:\n" + "\n".join([
                    f"User: {exchange['user']}\nAssistant: {exchange['assistant'][:100]}..."
                    for exchange in last_exchanges
                ])
    
            # Improved prompt construction for LLM with better context handling
            system_prompt = f"""
            You are an AI assistant for a smart farm system.
            Interpret the user's natural language command using the raw message, regex-derived metadata, 
            and the following system information.
            
            Be proactive and helpful - try to understand what the user wants to accomplish rather than
            focusing only on literal commands. Farmers speak naturally about their fields and equipment.

            System Information: {system_info_summary}

            {memory_context}

            If the intent is genuinely ambiguous with no way to determine what the user wants,
            return:
            {{
                "intent_type": "clarification_needed",
                "clarification": "<a polite and concise question to ask the user>"
            }}

            However, if you can reasonably infer the intent from context, prior conversation,
            or common farming requests, DO NOT ask for clarification. Make your best judgment.

            Return a structured intent object like:
            {{
                "intent_type": "<control_actuators|query_state|resource_management|...>",
                "action": "<close_actuator|get_resource_level|...>",
                "entities": {{
                    "actuator_ids": [...],
                    "field_ids": [...],
                    "resource_ids": [...]
                }},
                "parameters": {{
                    "new_status": "<open|close>", ...
                }}
            }}

            Remember that farmers often speak in natural terms. They might say "water the north field" instead of "open valve WV-0100".
            Focus on what they're trying to accomplish, not just literal commands.
            """
    
            human_prompt = json.dumps({
                "user_request": state.user_request,
                "regex_signals": regex_signals,
                "entities": entities
            }, indent=2, cls=DateTimeEncoder)
    
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt)
            ]
    
            response = self.llm.invoke(messages)
            content = response.content
    
            # Try to parse JSON from the LLM response with improved error handling
            try:
                json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
                if json_match:
                    intent_json = json.loads(json_match.group(1))
                else:
                    # Try to extract JSON from the plain text response
                    json_match = re.search(r'({.*})', content, re.DOTALL)
                    if json_match:
                        intent_json = json.loads(json_match.group(1))
                    else:
                        intent_json = json.loads(content)
            except json.JSONDecodeError:
                # If JSON parsing fails, try to infer intent directly from the request
                # This reduces unnecessary clarification requests
                intent_json = self._infer_intent_from_request(state.user_request, entities)
    
            self._log(f"LLM intent: {intent_json}")
    
            # Process common request patterns if LLM gave a clarification but we can handle it
            if intent_json.get("intent_type") == "clarification_needed":
                # Try to match common patterns - significantly expanded to reduce clarifications
                request_lower = state.user_request.lower()
                
                # Check for field irrigation requests - very common operation
                if (("irrigate" in request_lower or "water" in request_lower) and 
                        (entities["field_names"] or "all" in request_lower)):
                    
                    # Handle "irrigate all fields" specially
                    if "all" in request_lower and not entities["field_names"]:
                        intent_json = {
                            "intent_type": "irrigation_control",
                            "action": "start_irrigation_all_fields",
                            "entities": {
                                "field_ids": [field.get("id") for field in self.system_info.get("fields", [])],
                                "field_names": [field.get("name") for field in self.system_info.get("fields", [])]
                            },
                            "parameters": {
                                "duration": 30  # Default 30-minute irrigation
                            }
                        }
                    else:
                        # Single or multiple field irrigation
                        field_ids = []
                        field_names = []
                        
                        # Get IDs for all named fields
                        for field_name in entities["field_names"]:
                            field_id = entities["field_name_to_id"].get(field_name.lower())
                            if field_id:
                                field_ids.append(field_id)
                                field_names.append(field_name)
                        
                        if field_ids:
                            intent_json = {
                                "intent_type": "irrigation_control",
                                "action": "start_irrigation",
                                "entities": {
                                    "field_ids": field_ids,
                                    "field_names": field_names
                                },
                                "parameters": {
                                    "duration": 30  # Default 30-minute irrigation
                                }
                            }
                
                # Check for irrigation stop requests
                elif (("stop" in request_lower or "end" in request_lower or "turn off" in request_lower) and 
                      ("irrigation" in request_lower or "watering" in request_lower)):
                    
                    # Handle "stop all irrigation" specially
                    if "all" in request_lower and not entities["field_names"]:
                        # Find all currently irrigating fields
                        irrigating_fields = []
                        irrigating_names = []
                        
                        for field_id, status in self.status_cache.get("field_status", {}).items():
                            if status.get("is_irrigating", False):
                                irrigating_fields.append(field_id)
                                # Find field name
                                for field in self.system_info.get("fields", []):
                                    if field.get("id") == field_id:
                                        irrigating_names.append(field.get("name", ""))
                                        break
                        
                        if irrigating_fields:
                            intent_json = {
                                "intent_type": "irrigation_control",
                                "action": "stop_irrigation",
                                "entities": {
                                    "field_ids": irrigating_fields,
                                    "field_names": irrigating_names
                                },
                                "parameters": {}
                            }
                        else:
                            # No fields currently irrigating
                            intent_json = {
                                "intent_type": "information",
                                "action": "get_irrigation_status",
                                "entities": {},
                                "parameters": {}
                            }
                    elif entities["field_names"]:
                        # Stop irrigation for specific fields
                        field_ids = []
                        field_names = []
                        
                        # Get IDs for all named fields
                        for field_name in entities["field_names"]:
                            field_id = entities["field_name_to_id"].get(field_name.lower())
                            if field_id:
                                field_ids.append(field_id)
                                field_names.append(field_name)
                        
                        if field_ids:
                            intent_json = {
                                "intent_type": "irrigation_control",
                                "action": "stop_irrigation",
                                "entities": {
                                    "field_ids": field_ids,
                                    "field_names": field_names
                                },
                                "parameters": {}
                            }
                
                # Check for status requests about irrigation
                elif ("status" in request_lower or "check" in request_lower or 
                      "how is" in request_lower or "tell me about" in request_lower):
                    
                    # Check for field-specific status
                    if entities["field_names"]:
                        field_ids = []
                        field_names = []
                        
                        # Get IDs for all named fields
                        for field_name in entities["field_names"]:
                            field_id = entities["field_name_to_id"].get(field_name.lower())
                            if field_id:
                                field_ids.append(field_id)
                                field_names.append(field_name)
                        
                        if field_ids:
                            # Determine what aspect of the field they're asking about
                            if "irrigation" in request_lower or "watering" in request_lower:
                                intent_json = {
                                    "intent_type": "query_state",
                                    "action": "get_field_irrigation_status",
                                    "entities": {
                                        "field_ids": field_ids,
                                        "field_names": field_names
                                    },
                                    "parameters": {}
                                }
                            elif "moisture" in request_lower or "wetness" in request_lower or "humid" in request_lower:
                                intent_json = {
                                    "intent_type": "query_state",
                                    "action": "get_moisture_readings",
                                    "entities": {
                                        "field_ids": field_ids,
                                        "field_names": field_names
                                    },
                                    "parameters": {}
                                }
                            elif "temperature" in request_lower or "temp" in request_lower or "hot" in request_lower or "cold" in request_lower:
                                intent_json = {
                                    "intent_type": "query_state",
                                    "action": "get_temperature_readings",
                                    "entities": {
                                        "field_ids": field_ids,
                                        "field_names": field_names
                                    },
                                    "parameters": {}
                                }
                            else:
                                # General field status
                                intent_json = {
                                    "intent_type": "query_state",
                                    "action": "get_field_info",
                                    "entities": {
                                        "field_ids": field_ids,
                                        "field_names": field_names
                                    },
                                    "parameters": {}
                                }
                    else:
                        # General status queries
                        if "irrigation" in request_lower or "watering" in request_lower:
                            intent_json = {
                                "intent_type": "query_state",
                                "action": "get_all_irrigation_status",
                                "entities": {},
                                "parameters": {}
                            }
                        elif "equipment" in request_lower or "actuator" in request_lower or "device" in request_lower:
                            intent_json = {
                                "intent_type": "query_state",
                                "action": "get_all_actuator_status",
                                "entities": {},
                                "parameters": {}
                            }
                        elif "water" in request_lower or "level" in request_lower or "resource" in request_lower:
                            intent_json = {
                                "intent_type": "query_state",
                                "action": "get_resource_levels",
                                "entities": {},
                                "parameters": {}
                            }
                        else:
                            # General farm overview
                            intent_json = {
                                "intent_type": "query_state",
                                "action": "get_farm_overview",
                                "entities": {},
                                "parameters": {}
                            }
                
                # Check for equipment control - common operation
                elif (("open" in request_lower or "activate" in request_lower or "start" in request_lower or 
                       "turn on" in request_lower or "close" in request_lower or "deactivate" in request_lower or 
                       "stop" in request_lower or "turn off" in request_lower) and
                      ("valve" in request_lower or "pump" in request_lower or "equipment" in request_lower or
                       "device" in request_lower)):
                    
                    new_status = "open" if ("open" in request_lower or "activate" in request_lower or 
                                          "start" in request_lower or "turn on" in request_lower) else "close"
                    
                    # Check if specific actuators are mentioned
                    if entities["actuator_ids"]:
                        intent_json = {
                            "intent_type": "control_actuators",
                            "action": f"{new_status}_actuator",
                            "entities": {
                                "actuator_ids": entities["actuator_ids"]
                            },
                            "parameters": {
                                "new_status": new_status
                            }
                        }
                    elif entities["field_names"]:
                        # Control actuators in specific fields
                        field_ids = []
                        field_names = []
                        
                        # Get IDs for all named fields
                        for field_name in entities["field_names"]:
                            field_id = entities["field_name_to_id"].get(field_name.lower())
                            if field_id:
                                field_ids.append(field_id)
                                field_names.append(field_name)
                        
                        if field_ids:
                            # Try to determine actuator type from request
                            actuator_type = None
                            if "valve" in request_lower:
                                actuator_type = "water_valves"
                            elif "pump" in request_lower:
                                actuator_type = "pump"
                            elif "fertilizer" in request_lower:
                                actuator_type = "fertilizer_dispensers"
                            
                            intent_json = {
                                "intent_type": "control_actuators",
                                "action": f"{new_status}_field_actuators",
                                "entities": {
                                    "field_ids": field_ids,
                                    "field_names": field_names
                                },
                                "parameters": {
                                    "new_status": new_status,
                                    "actuator_type": actuator_type
                                }
                            }
                
                # Check for moisture queries
                elif entities["is_moisture_query"] and entities["field_names"]:
                    field_ids = []
                    field_names = []
                    
                    # Get IDs for all named fields
                    for field_name in entities["field_names"]:
                        field_id = entities["field_name_to_id"].get(field_name.lower())
                        if field_id:
                            field_ids.append(field_id)
                            field_names.append(field_name)
                    
                    if field_ids:
                        intent_json = {
                            "intent_type": "query_state",
                            "action": "get_moisture_readings",
                            "entities": {
                                "field_ids": field_ids,
                                "field_names": field_names
                            },
                            "parameters": {}
                        }
                
                # Check for temperature queries
                elif entities["is_temperature_query"] and entities["field_names"]:
                    field_ids = []
                    field_names = []
                    
                    # Get IDs for all named fields
                    for field_name in entities["field_names"]:
                        field_id = entities["field_name_to_id"].get(field_name.lower())
                        if field_id:
                            field_ids.append(field_id)
                            field_names.append(field_name)
                    
                    if field_ids:
                        intent_json = {
                            "intent_type": "query_state",
                            "action": "get_temperature_readings",
                            "entities": {
                                "field_ids": field_ids,
                                "field_names": field_names
                            },
                            "parameters": {}
                        }
                
                # Check for resource level queries
                elif ("water" in request_lower or "resource" in request_lower or "tank" in request_lower or 
                      "supply" in request_lower or "reservoir" in request_lower) and ("level" in request_lower or "how much" in request_lower or "status" in request_lower):
                    
                    # Handle specific resource queries
                    if entities["resource_ids"]:
                        intent_json = {
                            "intent_type": "query_state",
                            "action": "get_resource_levels",
                            "entities": {
                                "resource_ids": entities["resource_ids"]
                            },
                            "parameters": {}
                        }
                    else:
                        # Try to determine resource type
                        resource_type = None
                        if "water" in request_lower:
                            resource_type = "water"
                        elif "fertilizer" in request_lower:
                            resource_type = "fertilizer"
                        
                        intent_json = {
                            "intent_type": "query_state",
                            "action": "get_resource_levels",
                            "entities": {},
                            "parameters": {
                                "resource_type": resource_type
                            }
                        }
            
            # Update recent mentions for better continuity in future requests
            if intent_json != {"intent_type": "clarification_needed"}:
                # Update field mentions
                if "entities" in intent_json and "field_names" in intent_json["entities"] and intent_json["entities"]["field_names"]:
                    self.recent_mentions["fields"] = intent_json["entities"]["field_names"]
                
                # Update actuator mentions
                if "entities" in intent_json and "actuator_ids" in intent_json["entities"] and intent_json["entities"]["actuator_ids"]:
                    self.recent_mentions["actuators"] = intent_json["entities"]["actuator_ids"]
                
                # Update resource mentions
                if "entities" in intent_json and "resource_ids" in intent_json["entities"] and intent_json["entities"]["resource_ids"]:
                    self.recent_mentions["resources"] = intent_json["entities"]["resource_ids"]
            
            
            
            updated_state = FarmChatState(
                messages=state.messages,
                user_request=state.user_request,
                intent=intent_json,
                debug_logs=state.debug_logs + ["Intent extraction completed"]
            )
            return updated_state
            
        except Exception as e:
            error_message = f"Error analyzing request: {str(e)}"
            self._log(error_message)
            return FarmChatState(
                messages=state.messages,
                user_request=state.user_request,
                intent=None,
                error_occurred=True,
                error_message=error_message,
                debug_logs=state.debug_logs + [error_message]
            )
    
    
    
    # Enhanced method to execute the action plan with better actuator control
    def _execute_action_plan(self, state: FarmChatState) -> FarmChatState:
        """Execute the action plan and collect results with enhanced actuator control."""
        
        if self.debug_mode:
            state.debug_logs.append(f"Executing action plan with {len(state.plan)} steps")
        
        try:
            # Initialize execution results
            execution_results = []
            
            # Track field IDs and actuator IDs for dependency resolution
            field_id_map = {}
            actuator_lists = {}
            
            # Get all available actuators for validation
            all_actuators = self.farm_control_service.get_all_actuators()
            valid_actuator_ids = {actuator['id'] for actuator in all_actuators} if all_actuators else set()
            
            if self.debug_mode:
                state.debug_logs.append(f"Found {len(valid_actuator_ids)} valid actuator IDs")
            
            # First pass: Execute all information gathering actions
            for i, action in enumerate(state.plan):
                action_name = action.get("action")
                args = action.get("args", {})
                purpose = action.get("purpose", "")
                
                # Skip placeholder actions (they will be replaced with real actions)
                if action.get("is_placeholder", False):
                    continue
                    
                # Skip actuator control actions for now, we'll handle them in the second pass
                if action_name == "update_actuator_status":
                    continue
                
                if self.debug_mode:
                    state.debug_logs.append(f"Executing info gathering action {i+1}: {action_name} - {purpose}")
                
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
                    
                    # Handle special cases for gathering information needed by control actions
                    if action_name == "get_field_by_name":
                        # Store field ID for later use
                        if result and "id" in result:
                            field_name = args.get("field_name", "")
                            field_id_map[field_name.lower()] = result["id"]
                            if self.debug_mode:
                                state.debug_logs.append(f"Stored field ID for '{field_name}': {result['id']}")
                    
                    elif action_name == "get_actuators_by_field_name":
                        # Store actuators for later use
                        field_name = args.get("field_name", "")
                        if result:
                            actuator_lists[field_name.lower()] = result
                            if self.debug_mode:
                                state.debug_logs.append(f"Stored {len(result)} actuators for field '{field_name}'")
                    
                    elif action_name == "get_actuator_by_type":
                        # Store actuators for later use
                        actuator_type = args.get("actuator_type", "")
                        if result:
                            actuator_lists[actuator_type.lower()] = result
                            if self.debug_mode:
                                state.debug_logs.append(f"Stored {len(result)} actuators of type '{actuator_type}'")
                else:
                    if self.debug_mode:
                        state.debug_logs.append(f"Method {action_name} not found in farm_control_service")
            
            # Second pass: Execute control actions that directly specify an actuator ID
            for i, action in enumerate(state.plan):
                if action.get("action") != "update_actuator_status" or action.get("is_placeholder", True):
                    continue
                    
                args = action.get("args", {})
                purpose = action.get("purpose", "")
                actuator_id = args.get("actuator_id")
                new_status = args.get("new_status")
                
                # Skip placeholder actuator IDs
                if actuator_id == "ACTUATOR_ID_PLACEHOLDER":
                    continue
                    
                if self.debug_mode:
                    state.debug_logs.append(f"Executing direct actuator control: {purpose}")
                
                # Validate the actuator ID
                if actuator_id not in valid_actuator_ids:
                    # Record the failure
                    execution_result = {
                        "action": "update_actuator_status",
                        "args": args,
                        "purpose": purpose,
                        "result": {
                            "success": False, 
                            "error": f"Actuator ID {actuator_id} not found in the system"
                        }
                    }
                    execution_results.append(execution_result)
                    
                    if self.debug_mode:
                        state.debug_logs.append(f"Validation failed: Actuator ID {actuator_id} not found")
                    continue
                
                # Use the enhanced actuator update method with verification
                result = self._update_actuator_with_verification(actuator_id, new_status)
                
                # Store the result
                execution_result = {
                    "action": "update_actuator_status",
                    "args": args,
                    "purpose": purpose,
                    "result": result
                }
                execution_results.append(execution_result)
                
                if self.debug_mode:
                    success_msg = "succeeded" if result.get("success", False) else "failed"
                    state.debug_logs.append(f"Actuator control {success_msg} for {actuator_id}: {result.get('message', '')}")
            
            # Third pass: Handle placeholder actuator control actions
            for i, action in enumerate(state.plan):
                if not action.get("is_placeholder", False) or action.get("action") != "update_actuator_status":
                    continue
                    
                args = action.get("args", {}).copy()  # Create a copy to modify
                purpose = action.get("purpose", "")
                new_status = args.get("new_status")
                
                if self.debug_mode:
                    state.debug_logs.append(f"Processing placeholder action: {purpose}")
                
                # Handle field-specific actuator control
                if "field_name" in action:
                    field_name = action["field_name"].lower()
                    actuator_type = action.get("actuator_type", "").lower()
                    
                    # Get the actuators for this field
                    field_actuators = actuator_lists.get(field_name, [])
                    
                    if not field_actuators:
                        if self.debug_mode:
                            state.debug_logs.append(f"No actuators found for field '{field_name}'")
                        
                        # Try to get actuators on the fly if they're not already fetched
                        try:
                            field_actuators = self.farm_control_service.get_actuators_by_field_name(field_name, include_related=True)
                            if field_actuators:
                                actuator_lists[field_name] = field_actuators
                                if self.debug_mode:
                                    state.debug_logs.append(f"Retrieved {len(field_actuators)} actuators for field '{field_name}'")
                        except Exception as e:
                            if self.debug_mode:
                                state.debug_logs.append(f"Error retrieving actuators for field '{field_name}': {str(e)}")
                    
                    # Filter by actuator type if specified
                    if actuator_type and field_actuators:
                        filtered_actuators = [a for a in field_actuators if a.get("type", "").lower() == actuator_type]
                        if self.debug_mode:
                            state.debug_logs.append(f"Filtered {len(field_actuators)} actuators to {len(filtered_actuators)} of type '{actuator_type}'")
                        field_actuators = filtered_actuators
                    
                    # Control each actuator
                    if field_actuators:
                        for actuator in field_actuators:
                            if "id" in actuator:
                                actuator_id = actuator["id"]
                                
                                if self.debug_mode:
                                    state.debug_logs.append(f"Controlling actuator {actuator_id} in field '{field_name}'")
                                
                                # Use the enhanced actuator update method
                                result = self._update_actuator_with_verification(actuator_id, new_status)
                                
                                # Store the result
                                execution_result = {
                                    "action": "update_actuator_status",
                                    "args": {"actuator_id": actuator_id, "new_status": new_status},
                                    "purpose": f"{purpose} (Actuator ID: {actuator_id})",
                                    "result": result
                                }
                                execution_results.append(execution_result)
                                
                                if self.debug_mode:
                                    success_msg = "succeeded" if result.get("success", False) else "failed"
                                    state.debug_logs.append(f"Field actuator control {success_msg}: {result.get('message', '')}")
                    else:
                        if self.debug_mode:
                            state.debug_logs.append(f"No matching actuators found for field '{field_name}'{' of type ' + actuator_type if actuator_type else ''}")
                
                # Handle actuator type control
                elif "actuator_type" in action:
                    actuator_type = action["actuator_type"].lower()
                    
                    # Get actuators of this type
                    type_actuators = actuator_lists.get(actuator_type, [])
                    
                    if not type_actuators:
                        if self.debug_mode:
                            state.debug_logs.append(f"No actuators found of type '{actuator_type}'")
                        
                        # Try to get actuators on the fly
                        try:
                            type_actuators = self.farm_control_service.get_actuator_by_type(actuator_type, include_related=True)
                            if type_actuators:
                                actuator_lists[actuator_type] = type_actuators
                                if self.debug_mode:
                                    state.debug_logs.append(f"Retrieved {len(type_actuators)} actuators of type '{actuator_type}'")
                        except Exception as e:
                            if self.debug_mode:
                                state.debug_logs.append(f"Error retrieving actuators of type '{actuator_type}': {str(e)}")
                    
                    # Control each actuator
                    if type_actuators:
                        for actuator in type_actuators:
                            if "id" in actuator:
                                actuator_id = actuator["id"]
                                
                                if self.debug_mode:
                                    state.debug_logs.append(f"Controlling actuator {actuator_id} of type '{actuator_type}'")
                                
                                # Use the enhanced actuator update method
                                result = self._update_actuator_with_verification(actuator_id, new_status)
                                
                                # Store the result
                                execution_result = {
                                    "action": "update_actuator_status",
                                    "args": {"actuator_id": actuator_id, "new_status": new_status},
                                    "purpose": f"{purpose} (Actuator ID: {actuator_id})",
                                    "result": result
                                }
                                execution_results.append(execution_result)
                                
                                if self.debug_mode:
                                    success_msg = "succeeded" if result.get("success", False) else "failed"
                                    state.debug_logs.append(f"Type actuator control {success_msg}: {result.get('message', '')}")
                    else:
                        if self.debug_mode:
                            state.debug_logs.append(f"No actuators found of type '{actuator_type}'")
            
            # Update the state with execution results
            state.execution_results = execution_results
            
            # Check if any actuator control operations were attempted
            control_operations = [r for r in execution_results if r.get("action") == "update_actuator_status"]
            if control_operations:
                # Count successful and failed operations
                successful = sum(1 for op in control_operations if op.get("result", {}).get("success", False))
                failed = len(control_operations) - successful
                
                if self.debug_mode:
                    state.debug_logs.append(f"Completed {len(control_operations)} control operations: {successful} successful, {failed} failed")
                
                # Set error state if all operations failed
                if failed == len(control_operations) and len(control_operations) > 0:
                    state.error_occurred = True
                    state.error_message = f"All {failed} actuator control operations failed. Please check the system configuration."
                    if self.debug_mode:
                        state.debug_logs.append("All control operations failed, setting error state")
            
        except Exception as e:
            state.error_occurred = True
            state.error_message = f"Error executing action plan: {str(e)}"
            if self.debug_mode:
                state.debug_logs.append(f"Error in action plan execution: {str(e)}")
        
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
        
        confirmation_text = "Could you please confirm?"  # Fallback
        
        if state.confirmation_details and "confirmation_message" in state.confirmation_details:
            confirmation_text = state.confirmation_details["confirmation_message"]
        
        self.pending_confirmation = confirmation_text
        # Set the response so it gets returned to the client
        state.response = confirmation_text
        
        # Add message to chat history
        state.messages.append({
            "role": "assistant",
            "content": confirmation_text
        })
        
        # Reset confirmation flag (or keep it until user replies, depending on your flow)
        state.confirmation_needed = False
        self.pending_confirmation = None
        
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
    
   
    def _infer_intent_from_request(self, user_request: str, entities: dict) -> dict:
        """
        Infer intent directly from the user request when structured parsing fails.
        This is a fallback to reduce unnecessary clarification requests.
        
        Args:
            user_request: The user's raw request text
            entities: Previously extracted entities
            
        Returns:
            A basic intent dictionary
        """
        user_request_lower = user_request.lower()
        
        # Check for common request patterns
        if "irrigate" in user_request_lower or "water" in user_request_lower:
            # Irrigation request
            field_names = entities.get("field_names", [])
            if field_names:
                return {
                    "intent_type": "irrigation_control",
                    "action": "start_irrigation",
                    "entities": {
                        "field_ids": entities.get("field_name_to_id", {}).values(),
                        "field_names": field_names
                    },
                    "parameters": {
                        "duration": 30  # Default 30-minute irrigation
                    }
                }
            elif "all" in user_request_lower:
                # "irrigate all fields"
                return {
                    "intent_type": "irrigation_control",
                    "action": "start_irrigation_all_fields",
                    "entities": {},
                    "parameters": {
                        "duration": 30
                    }
                }
        
        elif "stop" in user_request_lower and ("irrigation" in user_request_lower or "watering" in user_request_lower):
            # Stop irrigation request
            field_names = entities.get("field_names", [])
            if field_names:
                return {
                    "intent_type": "irrigation_control",
                    "action": "stop_irrigation",
                    "entities": {
                        "field_ids": entities.get("field_name_to_id", {}).values(),
                        "field_names": field_names
                    },
                    "parameters": {}
                }
            elif "all" in user_request_lower:
                # "stop all irrigation"
                return {
                    "intent_type": "irrigation_control",
                    "action": "stop_irrigation_all_fields",
                    "entities": {},
                    "parameters": {}
                }
        
        elif "status" in user_request_lower or "how is" in user_request_lower or "check" in user_request_lower:
            # Status check request
            if entities.get("field_names"):
                return {
                    "intent_type": "query_state",
                    "action": "get_field_info",
                    "entities": {
                        "field_names": entities.get("field_names", []),
                        "field_ids": entities.get("field_name_to_id", {}).values()
                    },
                    "parameters": {}
                }
            elif "water" in user_request_lower or "resource" in user_request_lower:
                return {
                    "intent_type": "query_state",
                    "action": "get_resource_levels",
                    "entities": {},
                    "parameters": {}
                }
            else:
                return {
                    "intent_type": "query_state",
                    "action": "get_farm_overview",
                    "entities": {},
                    "parameters": {}
                }
        
        elif ("open" in user_request_lower or "close" in user_request_lower or 
            "turn on" in user_request_lower or "turn off" in user_request_lower):
            # Actuator control request
            actuator_ids = entities.get("actuator_ids", [])
            if actuator_ids:
                new_status = "open" if ("open" in user_request_lower or "turn on" in user_request_lower) else "close"
                return {
                    "intent_type": "control_actuators",
                    "action": f"{new_status}_actuator",
                    "entities": {
                        "actuator_ids": actuator_ids
                    },
                    "parameters": {
                        "new_status": new_status
                    }
                }
        
        # If we can't infer a specific intent, we need clarification
        return {
            "intent_type": "clarification_needed",
            "clarification": "I'm not sure what you'd like to do. Could you be more specific about what part of the farm system you want to control or check?"
        }
        

    # Update routing functions to handle max iterations
    def _route_after_intent_parsing(self, state: FarmChatState) -> str:
        """Determine the next step after intent parsing."""
        if state.current_iteration >= state.max_iterations:
            state.error_occurred = True
            state.error_message = "Maximum number of processing iterations reached."
            return "max_iterations_reached"
            
        if state.error_occurred:
            return "error_occurred"
        elif state.clarification_needed:
            return "clarification_needed"
        else:
            return "proceed"

    def _route_after_context_gathering(self, state: FarmChatState) -> str:
        """Determine the next step after context gathering."""
        if state.current_iteration >= state.max_iterations:
            state.error_occurred = True
            state.error_message = "Maximum number of processing iterations reached."
            return "max_iterations_reached"
            
        if state.error_occurred:
            return "error_occurred"
        else:
            return "proceed"

    def _route_after_plan_creation(self, state: FarmChatState) -> str:
        """Determine the next step after plan creation."""
        if state.current_iteration >= state.max_iterations:
            state.error_occurred = True
            state.error_message = "Maximum number of processing iterations reached."
            return "max_iterations_reached"
            
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
        if state.current_iteration >= state.max_iterations:
            state.error_occurred = True
            state.error_message = "Maximum number of processing iterations reached."
            return "max_iterations_reached"
        
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
        if state.current_iteration >= state.max_iterations:
            state.error_occurred = True
            state.error_message = "Maximum number of processing iterations reached."
            return "max_iterations_reached"
            
        if state.error_occurred:
            return "error_occurred"
        else:
            return "proceed"

    def process_message(self, user_message: str) -> Dict:
        """Process a message from the user with improved conversation context and direct command handling."""
    
        # Initialize the state
        state = FarmChatState(
            messages=[{"role": "user", "content": user_message}],
            user_request=user_message,
            debug_logs=[] if self.debug_mode else None
        )
        
        # Check if we're waiting for confirmation on a previous action
        if self.pending_confirmation:
            confirmation_input = user_message.strip().lower()
            
            if confirmation_input in ["yes", "y", "confirm", "sure", "do it", "go ahead"]:
                # User confirmed - proceed with the pending action
                if self.debug_mode:
                    state.debug_logs.append("User confirmed action. Proceeding with execution.")
                
                # Restore the pending state 
                state.intent = self.pending_confirmation["intent"]
                state.plan = self.pending_confirmation["plan"]
                state.scenario = self.pending_confirmation["scenario"]
                
                # Execute the pending action
                try:
                    # Process the confirmed action directly
                    actuator_id = state.plan[0]["args"]["actuator_id"]
                    new_status = state.plan[0]["args"]["new_status"]
                    
                    # Execute the control operation
                    control_result = self._update_actuator_with_verification(actuator_id, new_status)
                    
                    # Set execution results
                    state.execution_results = [{
                        "action": "update_actuator_status",
                        "args": {"actuator_id": actuator_id, "new_status": new_status},
                        "purpose": f"Direct control: {new_status} {actuator_id}",
                        "result": control_result
                    }]
                    
                    # Generate response based on the result
                    if control_result["success"]:
                        state.response = f"Successfully {new_status}d actuator {actuator_id}. {control_result.get('message', '')}"
                    else:
                        state.response = f"Failed to {new_status} actuator {actuator_id}. {control_result.get('error', '')}"
                    
                    # Clear the pending confirmation
                    self.pending_confirmation = None
                    
                except Exception as e:
                    state.error_occurred = True
                    state.error_message = f"Error processing confirmed action: {str(e)}"
                    state.response = f"Sorry, there was an error executing the operation: {str(e)}"
                    if self.debug_mode:
                        state.debug_logs.append(f"Error after confirmation: {str(e)}")
                
            elif confirmation_input in ["no", "n", "cancel", "stop", "never mind"]:
                # User canceled - clear pending and respond
                state.response = "Okay, I've canceled that request."
                self.pending_confirmation = None
                
            else:
                # Unclear response - ask again
                state.response = self.pending_confirmation.get("confirmation_message", 
                    "Just to confirm, should I proceed with the plan?")
            
            # Add to messages if we have a response
            if state.response:
                state.messages.append({"role": "assistant", "content": state.response})
                return {
                    "response": state.response,
                    "messages": state.messages,
                    "debug_logs": state.debug_logs if self.debug_mode else None
                }

        # First try to process as direct actuator command
        direct_control_processed = self._process_direct_actuator_control(state)
        
        if not direct_control_processed:
            # If not a direct command, process through standard workflow
            if self.debug_mode:
                state.debug_logs.append("Processing through standard workflow")
            try:
                # Process through graph and convert result back to FarmChatState
                graph_result = self.graph.invoke(state)
                state = FarmChatState(**graph_result)
            except Exception as e:
                state.error_occurred = True
                state.error_message = f"Error processing request: {str(e)}"
                state.response = "I encountered an error while processing your request. Please try again with a different query."
                if self.debug_mode:
                    state.debug_logs.append(f"Graph execution error: {str(e)}")

        # Handle confirmation requests
        if state.confirmation_needed and not direct_control_processed:
            # Store the pending confirmation state
            self.pending_confirmation = {
                "intent": state.intent,
                "plan": state.plan,
                "scenario": state.scenario,
                "confirmation_message": state.confirmation_details.get("confirmation_message", 
                    "Should I proceed with this action?")
            }
            
            # Set the confirmation response
            state.response = self.pending_confirmation["confirmation_message"]
            
            # Clear confirmation flags in state since we're handling it
            state.confirmation_needed = False
            state.confirmation_details = None

        # Generate response if not already set
        if not state.response:
            state = self._generate_response(state)

        # Add to conversation memory
        if state.response:
            self.conversation_memory.append({
                "user": user_message,
                "assistant": state.response,
                "entities": {
                    "field": state.intent.get("entities", {}).get("fields", []) if state.intent else [],
                    "actuator": state.intent.get("entities", {}).get("actuators", []) if state.intent else [],
                    "resource": state.intent.get("entities", {}).get("resources", []) if state.intent else []
                },
                "timestamp": datetime.datetime.now()
            })
            
            # Keep conversation memory manageable
            if len(self.conversation_memory) > 10:
                self.conversation_memory = self.conversation_memory[-10:]

        # Add response to messages if not already there
        if state.response and (not state.messages or state.messages[-1]["content"] != state.response):
            state.messages.append({"role": "assistant", "content": state.response})

        # Format result
        result = {
            "response": state.response,
            "messages": state.messages
        }

        if self.debug_mode and state.debug_logs:
            result["debug_logs"] = state.debug_logs

        return result

    def _process_direct_actuator_control(self, state: FarmChatState) -> bool:
        """
        Improved direct actuator control processing with better ID recognition.
        Returns True if processed as direct command, False otherwise.
        """
        if not state.user_request:
            return False
            
        try:
            user_input = state.user_request.lower()
            
            # Define control command patterns
            open_pattern = r"\b(open|start|activate|turn\s+on|switch\s+on|enable|power\s+on)\b"
            close_pattern = r"\b(close|stop|deactivate|turn\s+off|switch\s+off|disable|shut(\s+down)?|power\s+off)\b"
            
            # Check for control commands
            has_open = bool(re.search(open_pattern, user_input))
            has_close = bool(re.search(close_pattern, user_input))
            
            if not (has_open or has_close):
                return False
                
            # Determine the requested status
            new_status = "open" if has_open else "close"
            
            # Enhanced actuator ID patterns
            id_patterns = [
                r'([A-Za-z]+-\d{4})',  # Standard format
                r'([A-Za-z]{2,4})(\d{4})',  # No hyphen
                r'id\s*:\s*([A-Za-z]+-?\d{4})',  # With "id:" prefix
                r'with\s+id\s*:?\s*([A-Za-z]+-?\d{4})',  # With "with id"
                r'(?:actuator|device|equipment|valve|pump)\s+([A-Za-z]+-?\d{4})'  # After actuator keywords
            ]
            
            # Try each pattern to find actuator ID
            actuator_id = None
            for pattern in id_patterns:
                match = re.search(pattern, state.user_request, re.IGNORECASE)
                if match:
                    # Handle different match group formats
                    if len(match.groups()) > 1:
                        # For patterns that split prefix and numbers
                        actuator_id = f"{match.group(1)}-{match.group(2)}"
                    else:
                        actuator_id = match.group(1)
                    
                    # Ensure proper formatting
                    actuator_id = actuator_id.upper()
                    if '-' not in actuator_id and len(actuator_id) >= 6:
                        # Format as XX-XXXX if missing hyphen
                        actuator_id = f"{actuator_id[:2]}-{actuator_id[2:]}"
                    break
            
            if not actuator_id:
                return False
                
            if self.debug_mode:
                state.debug_logs.append(f"Direct actuator control detected: {new_status} {actuator_id}")
            
            # Validate actuator exists
            if not self._validate_actuator_id(actuator_id):
                state.error_occurred = True
                state.error_message = f"Actuator {actuator_id} not found in the system"
                state.execution_results = [{
                    "action": "update_actuator_status",
                    "args": {"actuator_id": actuator_id, "new_status": new_status},
                    "purpose": f"Direct control: {new_status} {actuator_id}",
                    "result": {
                        "success": False,
                        "error": f"Actuator {actuator_id} not found in the system"
                    }
                }]
                state.scenario = "actuator_control"
                state.intent = {
                    "intent_category": "control_operation",
                    "specific_intent": f"Control actuator {actuator_id}",
                    "entities": {"actuators": [actuator_id]}
                }
                return True
            
            # Get current status for comparison
            current_actuator = self.farm_control_service.get_actuator_by_id(actuator_id)
            current_status = current_actuator.get("status") if current_actuator else None
            
            # Check if already in desired state
            if current_status == new_status:
                state.response = f"Actuator {actuator_id} is already {new_status}. No change needed."
                return True
            
            # Prepare confirmation details
            confirmation_message = f"I'll {new_status} actuator {actuator_id}. Would you like me to proceed?"
            
            # Check if this is a confirmation of a previous request
            if (self.pending_confirmation and 
                self.pending_confirmation.get("intent", {}).get("entities", {}).get("actuators", []) == [actuator_id]):
                # User confirmed - proceed with the control
                control_result = self._update_actuator_with_verification(actuator_id, new_status)
                
                # Set execution results
                state.execution_results = [{
                    "action": "update_actuator_status",
                    "args": {"actuator_id": actuator_id, "new_status": new_status},
                    "purpose": f"Direct control: {new_status} {actuator_id}",
                    "result": control_result
                }]
                
                # Setup scenario and intent
                state.scenario = "actuator_control"
                state.intent = {
                    "intent_category": "control_operation",
                    "specific_intent": f"Control actuator {actuator_id}",
                    "entities": {"actuators": [actuator_id]}
                }
                
                # Clear pending confirmation
                self.pending_confirmation = None
                
                # Run impact analysis
                state = self._analyze_impact(state)
                
                return True
            else:
                # New request - ask for confirmation
                self.pending_confirmation = {
                    "intent": {
                        "intent_category": "control_operation",
                        "specific_intent": f"Control actuator {actuator_id}",
                        "entities": {"actuators": [actuator_id]}
                    },
                    "plan": [{
                        "action": "update_actuator_status",
                        "args": {"actuator_id": actuator_id, "new_status": new_status},
                        "purpose": f"Direct control: {new_status} {actuator_id}"
                    }],
                    "scenario": "actuator_control",
                    "confirmation_message": confirmation_message
                }
                
                state.response = confirmation_message
                return True
                
        except Exception as e:
            if self.debug_mode:
                state.debug_logs.append(f"Error in direct actuator control: {str(e)}")
            return False
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
    
    def _create_system_context(self) -> str:
        """Create a comprehensive system context string for the LLM."""
        
        context = [
            "You are an AI assistant managing a smart farm system with the following components:",
            f"\nFarms: {len(self.system_info.get('farms', []))} total farms",
            f"Fields: {len(self.system_info.get('fields', []))} total fields",
            f"Sensors: {len(self.system_info.get('sensors', []))} total sensors",
            f"Actuators: {len(self.system_info.get('actuators', []))} total actuators",
            f"Resources: {len(self.system_info.get('resources', []))} total resources",
            "\nAvailable fields:",
        ]
        
        # Add field information
        for field in self.system_info.get('fields', []):
            field_name = field.get('name', 'Unknown')
            field_crop = field.get('crop', 'Unknown')
            context.append(f"- {field_name} (Crop: {field_crop})")
        
        # Add actuator types
        actuator_types = set(a.get('type', 'Unknown') for a in self.system_info.get('actuators', []))
        context.append("\nAvailable actuator types:")
        for a_type in actuator_types:
            context.append(f"- {a_type}")
        
        # Add resource information
        context.append("\nAvailable resources:")
        for resource in self.system_info.get('resources', []):
            resource_name = resource.get('name', 'Unknown')
            resource_type = resource.get('type', 'Unknown')
            context.append(f"- {resource_name} ({resource_type})")
        
        # Add available functions
        context.append("\nAvailable control functions:")
        for func_name, func_info in FUNCTION_DESCRIPTIONS.items():
            desc = func_info.get('description', '')
            args = func_info.get('args', {})
            args_str = ', '.join(f"{k}: {v}" for k, v in args.items())
            context.append(f"- {func_name}: {desc}")
            if args_str:
                context.append(f"  Arguments: {args_str}")
        
        return "\n".join(context)
    
    
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
    
    
    # Enhanced methods for actuator control in the EnhancedFarmChatInterface class

    def _validate_actuator_id(self, actuator_id: str) -> bool:
        """
        Validate that an actuator ID exists in the system.
        Returns True if the actuator exists, False otherwise.
        """
        try:
            actuator = self.farm_control_service.get_actuator_by_id(actuator_id)
            return actuator is not None and 'id' in actuator
        except Exception as e:
            if self.debug_mode:
                self._log(f"Error validating actuator ID {actuator_id}: {str(e)}")
            return False

    def _verify_actuator_status_change(self, actuator_id: str, expected_status: str, max_retries: int = 3) -> dict:
        """
        Verify that an actuator's status was successfully changed to the expected status.
        Includes retry logic to account for potential delays in status updates.
        
        Returns a dict with:
        - success: Boolean indicating if verification was successful
        - actual_status: The actual status of the actuator
        - message: Description of the verification result
        """
        import time
        
        for attempt in range(max_retries):
            try:
                # Get the current actuator status
                actuator = self.farm_control_service.get_actuator_by_id(actuator_id)
                
                if not actuator:
                    return {
                        "success": False, 
                        "actual_status": None,
                        "message": f"Failed to retrieve actuator {actuator_id} for verification"
                    }
                
                actual_status = actuator.get("status")
                
                # Check if the status matches what we expect
                if actual_status == expected_status:
                    return {
                        "success": True,
                        "actual_status": actual_status,
                        "message": f"Actuator {actuator_id} status successfully changed to {expected_status}"
                    }
                
                # If this isn't our last attempt, wait briefly before retrying
                if attempt < max_retries - 1:
                    time.sleep(0.5)  # Wait half a second between retries
                
            except Exception as e:
                if self.debug_mode:
                    self._log(f"Error during attempt {attempt+1} to verify actuator {actuator_id} status: {str(e)}")
                
                # If this isn't our last attempt, continue to the next one
                if attempt < max_retries - 1:
                    continue
                
                # Otherwise, return failure
                return {
                    "success": False,
                    "actual_status": None,
                    "message": f"Error verifying actuator status: {str(e)}"
                }
        
        # If we've exhausted all retries and still haven't returned, the status didn't change
        return {
            "success": False,
            "actual_status": actual_status if 'actual_status' in locals() else None,
            "message": f"Actuator {actuator_id} status did not change to {expected_status} after {max_retries} verification attempts"
        }

    def _update_actuator_with_verification(self, actuator_id: str, new_status: str) -> dict:
        """
        Update an actuator's status and verify the change was successful.
        This is a wrapper around update_actuator_status with added verification.
        
        Returns a dict with the result of the operation, including verification details.
        """
        if self.debug_mode:
            self._log(f"Starting update for actuator {actuator_id} to status {new_status}")
        
        if not self._validate_actuator_id(actuator_id):
            if self.debug_mode:
                self._log(f"Validation failed: Invalid actuator ID {actuator_id}")
            return {
                "success": False,
                "error": f"Invalid actuator ID: {actuator_id}",
                "verification": None
            }
        
        try:
            # Get current status first to check if we're actually changing anything
            current_actuator = self.farm_control_service.get_actuator_by_id(actuator_id)
            current_status = current_actuator.get("status") if current_actuator else None
            
            if self.debug_mode:
                self._log(f"Current status of actuator {actuator_id}: {current_status}")
            
            if current_status == new_status:
                if self.debug_mode:
                    self._log(f"No change needed: Actuator {actuator_id} is already in {new_status} status")
                return {
                    "success": True,
                    "message": f"Actuator {actuator_id} is already in {new_status} status. No change needed.",
                    "verification": {"success": True, "actual_status": current_status}
                }
            
            # Execute the status update
            if self.debug_mode:
                self._log(f"Updating actuator {actuator_id} to status {new_status}")
            result = self.farm_control_service.update_actuator_status(actuator_id=actuator_id, new_status=new_status)
            
            if self.debug_mode:
                self._log(f"Update result for actuator {actuator_id}: {result}")
            
            # Verify the change was successful
            if self.debug_mode:
                self._log(f"Verifying status change for actuator {actuator_id} to {new_status}")
            verification = self._verify_actuator_status_change(actuator_id, new_status)
            
            if self.debug_mode:
                self._log(f"Verification result for actuator {actuator_id}: {verification}")
            
            # Combine the initial result with verification
            combined_result = {
                "success": verification["success"],
                "original_result": result,
                "verification": verification
            }
            
            # Add extra context to the result
            if verification["success"]:
                combined_result["message"] = f"Successfully updated actuator {actuator_id} status to {new_status}"
                if self.debug_mode:
                    self._log(f"Actuator {actuator_id} successfully updated to {new_status}")
            else:
                combined_result["error"] = verification["message"]
                combined_result["message"] = f"Failed to update actuator {actuator_id} status to {new_status}"
                if self.debug_mode:
                    self._log(f"Failed to update actuator {actuator_id} to {new_status}: {verification['message']}")
            
            return combined_result
            
        except Exception as e:
            error_msg = f"Error updating actuator {actuator_id} status: {str(e)}"
            if self.debug_mode:
                self._log(error_msg)
            
            return {
                "success": False,
                "error": error_msg,
                "verification": None
            }

    

    def _analyze_impact(self, state: FarmChatState) -> FarmChatState:
        """Analyze the impact of the executed actions with enhanced actuator status reporting."""
    
        if self.debug_mode:
            state.debug_logs.append("Analyzing impact of executed actions")
        
        try:
            # Initialize impact analysis structure
            impact = {
                "summary": "",
                "details": {},
                "status_changes": [],
                "resource_impacts": [],
                "recommendations": [],
                "control_operations": {
                    "total": 0,
                    "successful": 0,
                    "failed": 0,
                    "details": []
                }
            }
            
            # Get execution results
            execution_results = state.execution_results or []
            
            # Group results by action type for easier analysis
            action_results = {}
            for result in execution_results:
                action = result.get("action")
                action_results.setdefault(action, []).append(result)
            
            # Analyze actuator control operations
            actuator_updates = action_results.get("update_actuator_status", [])
            if actuator_updates:
                # Count total operations
                impact["control_operations"]["total"] = len(actuator_updates)
                
                # Track successful status changes
                actuator_status_changes = []
                
                for update in actuator_updates:
                    args = update.get("args", {})
                    result = update.get("result", {})
                    actuator_id = args.get("actuator_id")
                    new_status = args.get("new_status")
                    purpose = update.get("purpose", "")
                    
                    # Was this operation successful?
                    success = result.get("success", False)
                    
                    # Add to appropriate counter
                    if success:
                        impact["control_operations"]["successful"] += 1
                    else:
                        impact["control_operations"]["failed"] += 1
                    
                    # Add details for this operation
                    operation_detail = {
                        "actuator_id": actuator_id,
                        "requested_status": new_status,
                        "success": success,
                        "purpose": purpose
                    }
                    
                    # Add verification details if available
                    if "verification" in result:
                        verification = result.get("verification", {})
                        operation_detail["actual_status"] = verification.get("actual_status")
                        operation_detail["verification_message"] = verification.get("message")
                    
                    # Add error message if present
                    if "error" in result:
                        operation_detail["error"] = result.get("error")
                    
                    impact["control_operations"]["details"].append(operation_detail)
                    
                    # Track successful status changes for summary
                    if success:
                        actuator_status_changes.append({
                            "actuator_id": actuator_id,
                            "new_status": new_status,
                            "purpose": purpose
                        })
            
            # Check for resource level changes
            resource_level_results = action_results.get("get_resource_levels", [])
            if len(resource_level_results) >= 2:
                resource_levels_before = resource_level_results[0].get("result")
                resource_levels_after = resource_level_results[-1].get("result")
                
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
            
            # Build impact summary based on actual results
            if impact["control_operations"]["total"] > 0:
                successful = impact["control_operations"]["successful"]
                failed = impact["control_operations"]["failed"]
                total = impact["control_operations"]["total"]
                
                if successful > 0 and failed == 0:
                    impact["summary"] = f"All {total} actuator control operations completed successfully."
                elif successful > 0 and failed > 0:
                    impact["summary"] = f"Partially completed: {successful} of {total} actuator control operations succeeded, {failed} failed."
                elif successful == 0 and failed > 0:
                    impact["summary"] = f"Failed to complete any of the {total} actuator control operations."
                
                # Add details about what was changed
                if actuator_status_changes:
                    open_count = sum(1 for change in actuator_status_changes if change["new_status"] == "open")
                    closed_count = sum(1 for change in actuator_status_changes if change["new_status"] == "close")
                    
                    status_details = []
                    if open_count > 0:
                        status_details.append(f"Opened {open_count} actuator{'s' if open_count > 1 else ''}")
                    if closed_count > 0:
                        status_details.append(f"Closed {closed_count} actuator{'s' if closed_count > 1 else ''}")
                    
                    if status_details:
                        impact["summary"] += f" {' and '.join(status_details)}."
                    
                    impact["status_changes"] = actuator_status_changes
            else:
                # Information retrieval only
                impact["summary"] = "Retrieved information from the farm system."
            
            # Generate intelligent recommendations based on actions and results
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
            
            # Recommend follow-up actions based on control operations
            if impact["control_operations"]["successful"] > 0:
                # If we opened irrigation valves, recommend checking after some time
                if any(change["new_status"] == "open" for change in actuator_status_changes):
                    recommendations.append({
                        "type": "follow_up",
                        "message": "Irrigation has been started. Consider checking field moisture levels in a few hours."
                    })
                
                # If operations failed, recommend investigation
                if impact["control_operations"]["failed"] > 0:
                    recommendations.append({
                        "type": "warning",
                        "message": f"{impact['control_operations']['failed']} control operations failed. Consider checking the system for issues."
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
        """Generate a human-friendly response with accurate actuator control results."""
    
        if self.debug_mode:
            state.debug_logs.append("Generating response with accurate actuator control feedback")
        
        # ✅ Don't overwrite existing messages like confirmations
        if state.response:
            if self.debug_mode:
                state.debug_logs.append("Response already set, skipping response generation.")
            state.messages.append({"role": "assistant", "content": state.response})
            return state
        
        try:
            # For actuator control operations, create a specialized response based on verified results
            if state.scenario in ["actuator_control", "irrigation_control"]:
                # Find all actuator operations in the execution results
                actuator_operations = []
                for result in state.execution_results or []:
                    if result.get("action") == "update_actuator_status":
                        actuator_operations.append(result)
                
                if actuator_operations:
                    # Get counts
                    total_ops = len(actuator_operations)
                    successful_ops = sum(1 for op in actuator_operations 
                                        if op.get("result", {}).get("success", False))
                    failed_ops = total_ops - successful_ops
                    
                    # For clarity, get details of what was done
                    actuator_details = []
                    for op in actuator_operations:
                        args = op.get("args", {})
                        result = op.get("result", {})
                        
                        actuator_id = args.get("actuator_id", "unknown")
                        status = args.get("new_status", "unknown")
                        success = result.get("success", False)
                        
                        # Get verification details if available
                        verification = result.get("verification", {})
                        actual_status = verification.get("actual_status") if verification else None
                        
                        actuator_details.append({
                            "id": actuator_id,
                            "requested_status": status,
                            "success": success,
                            "actual_status": actual_status,
                            "error": result.get("error", "")
                        })
                    
                    # Create a response based on the actual results
                    if successful_ops == total_ops:
                        # All operations succeeded
                        if total_ops == 1:
                            # Single actuator operation
                            act_id = actuator_details[0]["id"]
                            status = actuator_details[0]["requested_status"]
                            state.response = f"I've successfully {status}d the actuator {act_id}. The operation has been verified and completed."
                        else:
                            # Multiple actuator operations
                            state.response = f"I've successfully completed all {total_ops} actuator operations as requested. All changes have been verified."
                    
                    elif successful_ops > 0:
                        # Some operations succeeded, some failed
                        state.response = f"I've completed {successful_ops} out of {total_ops} requested actuator operations. {failed_ops} operations failed. "
                        
                        # Add details about the failures
                        failed_ids = [d["id"] for d in actuator_details if not d["success"]]
                        state.response += f"Could not change the status of the following actuators: {', '.join(failed_ids)}."
                    
                    else:
                        # All operations failed
                        if total_ops == 1:
                            # Single failed operation
                            act_id = actuator_details[0]["id"]
                            error = actuator_details[0]["error"] if actuator_details[0]["error"] else "The system could not verify the change"
                            state.response = f"I was unable to change the status of actuator {act_id}. {error}."
                        else:
                            # Multiple failed operations
                            state.response = f"I was unable to complete any of the {total_ops} requested actuator operations. "
                            
                            # Add some error information if available
                            errors = set(d["error"] for d in actuator_details if d["error"])
                            if errors:
                                state.response += f"Errors reported: {'; '.join(errors)}."
                            else:
                                state.response += "Please check the system status or try again."
                else:
                    # No actuator operations found but scenario is actuator_control
                    if state.error_occurred:
                        state.response = f"I encountered an error while trying to control the actuators: {state.error_message}"
                    else:
                        state.response = "I understood your request to control actuators, but I couldn't identify which specific actuators to operate. Could you please specify the actuator ID or type?"
            else:
                # For other scenarios, use the standard response generation
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
            if state.scenario == "irrigation_control" or state.scenario == "actuator_control":
                # Focus response on control operations
                control_ops = state.impact_analysis.get("control_operations", {}) if state.impact_analysis else {}
                successful = control_ops.get("successful", 0)
                failed = control_ops.get("failed", 0)
                total = control_ops.get("total", 0)
                
                if total > 0:
                    if successful > 0 and failed == 0:
                        basic_response = f"I've successfully completed all {total} control operations you requested for the farm system."
                    elif successful > 0 and failed > 0:
                        basic_response = f"I've completed {successful} out of {total} control operations. However, {failed} operations failed. Please check the system status."
                    else:
                        basic_response = f"I was unable to complete any of the {total} control operations you requested. There might be an issue with the system or the actuators."
                else:
                    basic_response = "I processed your control request, but no actuator operations were executed. Please try again with more specific instructions."
            else:
                basic_response = "I processed your request about the farm system, but encountered an error generating a detailed response. The operation may have completed successfully. Please try checking the system status."
            
            state.response = basic_response
            if self.debug_mode:
                state.debug_logs.append(f"Error in response generation: {str(e)}")
                
            # Add the basic response to messages
            message = {
                "role": "assistant",
                "content": state.response
            }
            state.messages.append(message)
            
        return state
    
    def _get_actuator_information(self, field_name=None, actuator_type=None, actuator_id=None):
        """
        Get information about actuators based on different criteria.
        This helper method centralizes actuator information retrieval.
        
        Args:
            field_name: Optional name of field to get actuators for
            actuator_type: Optional type of actuators to retrieve
            actuator_id: Optional specific actuator ID
            
        Returns:
            List of actuator information dictionaries or a single actuator dict
        """
        try:
            if actuator_id:
                # Get a specific actuator by ID
                return self.farm_control_service.get_actuator_by_id(actuator_id)
            elif field_name:
                # Get actuators for a specific field
                actuators = self.farm_control_service.get_actuators_by_field_name(field_name, include_related=True)
                
                # Filter by type if specified
                if actuator_type and actuators:
                    return [a for a in actuators if a.get("type", "").lower() == actuator_type.lower()]
                return actuators
            elif actuator_type:
                # Get actuators of a specific type
                return self.farm_control_service.get_actuator_by_type(actuator_type, include_related=True)
            else:
                # Get all actuators
                return self.farm_control_service.get_all_actuators(include_related=True)
        except Exception as e:
            if self.debug_mode:
                self._log(f"Error getting actuator information: {str(e)}")
            return []

    def _create_irrigation_plan(self, state: FarmChatState) -> FarmChatState:
        """
        Create a specialized plan for irrigation control.
        This expands the _create_action_plan to handle irrigation scenarios more effectively.
        """
        # Skip if we're not in an irrigation scenario
        if state.scenario != "irrigation_control":
            return state
            
        try:
            # Get intent information
            intent = state.intent
            fields = intent.get("entities", {}).get("fields", [])
            operation = intent.get("operation", "").lower()
            
            # Determine the requested status
            new_status = "open" if any(op in operation for op in ["start", "open", "turn on", "activate"]) else "close"
            
            # Create plan steps
            plan = []
            
            # First check resource levels
            plan.append({
                "action": "get_resource_levels",
                "args": {},
                "purpose": "Check water resource levels before irrigation control"
            })
            
            # For each field, get actuators and plan to control them
            for field_name in fields:
                # Get field information
                plan.append({
                    "action": "get_field_by_name",
                    "args": {"field_name": field_name},
                    "purpose": f"Get information about field {field_name}"
                })
                
                # Get irrigation actuators for the field
                plan.append({
                    "action": "get_actuators_by_field_name",
                    "args": {"field_name": field_name, "include_related": True},
                    "purpose": f"Get irrigation actuators for field {field_name}"
                })
                
                # Add placeholder for the control operations
                plan.append({
                    "action": "update_actuator_status",
                    "args": {"actuator_id": "ACTUATOR_ID_PLACEHOLDER", "new_status": new_status},
                    "purpose": f"{new_status.capitalize()} irrigation for field {field_name}",
                    "is_placeholder": True,
                    "field_name": field_name,
                    "actuator_type": "water_valves"  # Assuming water_valves is the type for irrigation
                })
            
            # Check resource levels again after operations
            plan.append({
                "action": "get_resource_levels",
                "args": {},
                "purpose": "Check water resource levels after irrigation control"
            })
            
            # Prepare confirmation details
            confirmation_details = {
                "plan_summary": f"{'start' if new_status == 'open' else 'stop'} irrigation for field(s): {', '.join(fields)}",
                "confirmation_message": f"I'll {'open' if new_status == 'open' else 'close'} the irrigation valves for {', '.join(fields)}. The water level will be checked before proceeding. Would you like me to continue?"
            }
            
            # Update the state
            state.plan = plan
            state.confirmation_needed = True
            state.confirmation_details = confirmation_details
            
        except Exception as e:
            state.error_occurred = True
            state.error_message = f"Error creating irrigation plan: {str(e)}"
            if self.debug_mode:
                state.debug_logs.append(f"Error in irrigation plan creation: {str(e)}")
        
        return state

    def _validate_control_safety(self, actuator_operations):
        """
        Validate that a set of actuator control operations is safe to execute.
        Performs checks like:
        - Resource dependencies
        - Conflicting operations
        - System limits
        
        Args:
            actuator_operations: List of dictionaries with actuator_id and new_status
            
        Returns:
            Tuple of (is_safe, warning_message)
        """
        try:
            # Get all resources and their levels
            resources = self.farm_control_service.get_resource_levels()
            
            # Check water level for irrigation operations
            water_valves_opening = [op for op in actuator_operations 
                                if op.get("new_status") == "open" and 
                                (self._get_actuator_information(actuator_id=op.get("actuator_id", "")) or {}).get("type") == "water_valves"]
            
            if water_valves_opening:
                # Find water resources
                water_resources = [r_id for r_id, level in resources.items() 
                                if any(water_term in self.farm_control_service.get_resource_by_id(r_id).get("content", "").lower() 
                                        for water_term in ["water", "h2o", "irrigation"])]
                
                # Check if any water resource is below threshold
                low_water = False
                low_water_message = ""
                
                for resource_id in water_resources:
                    level = resources.get(resource_id, 100)
                    if level < 15:  # Critical threshold
                        resource_info = self.farm_control_service.get_resource_by_id(resource_id) or {}
                        resource_name = resource_info.get("name", f"Resource {resource_id}")
                        low_water = True
                        low_water_message = f"Warning: {resource_name} level is critically low at {level}%. Irrigation may not function properly."
                
                if low_water:
                    return False, low_water_message
            
            # Check for conflicting operations
            actuator_ids = set(op.get("actuator_id") for op in actuator_operations)
            if len(actuator_ids) < len(actuator_operations):
                return False, "Warning: Conflicting operations detected for the same actuator. This could cause system instability."
            
            # All checks passed
            return True, ""
            
        except Exception as e:
            # If validation fails, assume it's not safe
            return False, f"Safety validation failed: {str(e)}"
    
    def _update_status_cache(self):
        """Update the status cache if it's expired."""
        now = datetime.datetime.now()
        if (not self.status_cache["last_update"] or 
            now - self.status_cache["last_update"] > self.cache_lifetime):
            try:
                self.status_cache["active_actuators"] = self.farm_control_service.get_active_actuators()
                self.status_cache["inactive_actuators"] = self.farm_control_service.get_inactive_actuators()
                self.status_cache["resource_levels"] = self.farm_control_service.get_resource_levels()
                
                # Update field status
                for field in self.system_info.get("fields", []):
                    field_id = field.get("id")
                    if field_id:
                        # Check irrigation status
                        field_actuators = self.farm_control_service.get_actuators_by_field(field_id)
                        active_irrigation = any(
                            actuator.get("status") == "open" and 
                            actuator.get("type") in ["water_valves", "pump"] 
                            for actuator in field_actuators
                        )
                        
                        # Check soil moisture if available
                        moisture_sensors = [
                            sensor for sensor in self.farm_control_service.get_sensors_by_field(field_id)
                            if "moist" in sensor.get("type", "").lower()
                        ]
                        
                        self.status_cache["field_status"][field_id] = {
                            "is_irrigating": active_irrigation,
                            "has_moisture_sensors": len(moisture_sensors) > 0,
                            "actuators": field_actuators
                        }
                
                self.status_cache["last_update"] = now
            except Exception as e:
                self._log(f"Error updating status cache: {str(e)}")
    
    def get_system_overview(self):
        """Get a comprehensive overview of the farm system."""
        self._update_status_cache()
        
        overview = {
            "farm_info": {
                "total_farms": len(self.system_info.get("farms", [])),
                "total_fields": len(self.system_info.get("fields", [])),
                "total_equipment": len(self.system_info.get("actuators", [])),
                "total_sensors": len(self.system_info.get("sensors", []))
            },
            "active_equipment": {
                "count": len(self.status_cache.get("active_actuators", [])),
                "by_type": {}
            },
            "field_status": {},
            "resource_levels": {}
        }
        
        # Group active equipment by type
        for actuator in self.status_cache.get("active_actuators", []):
            actuator_type = actuator.get("type", "Unknown")
            if actuator_type not in overview["active_equipment"]["by_type"]:
                overview["active_equipment"]["by_type"][actuator_type] = []
            overview["active_equipment"]["by_type"][actuator_type].append(actuator.get("id"))
        
        # Summarize field status
        for field in self.system_info.get("fields", []):
            field_id = field.get("id")
            if field_id:
                field_status = self.status_cache.get("field_status", {}).get(field_id, {})
                overview["field_status"][field.get("name", "Unknown")] = {
                    "is_irrigating": field_status.get("is_irrigating", False),
                    "crop": field.get("crop", "Unknown"),
                    "area": field.get("area", "Unknown")
                }
        
        # Summarize resource levels
        for resource in self.system_info.get("resources", []):
            overview["resource_levels"][resource.get("name", "Unknown")] = {
                "current_level": resource.get("current_level", "Unknown"),
                "capacity": resource.get("capacity", "Unknown"),
                "content": resource.get("content", "Unknown")
            }
        
        return overview

    
    def chat(self, messages: List[Dict]) -> Dict:
        """
        Process a conversation with message history and return a response.
        Useful for maintaining context over multiple turns.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            
        Returns:
            Dict containing response and updated message history
        """
        if not messages or not isinstance(messages, list):
            return {
                "response": "Invalid message format",
                "messages": [],
                "error": "Messages must be a non-empty list"
            }
        
        # Get the latest user message
        latest_user_message = next((msg for msg in reversed(messages) if msg.get("role") == "user"), None)
        
        if not latest_user_message:
            return {
                "response": "No user message found",
                "messages": messages,
                "error": "No user message in conversation"
            }
        
        # Store previous messages for context
        self.conversation_memory = [
            {
                "user": msg["content"],
                "assistant": next((m["content"] for m in messages[i+1:] if m["role"] == "assistant"), None),
                "timestamp": datetime.datetime.now() - datetime.timedelta(seconds=(len(messages)-i))
            }
            for i, msg in enumerate(messages[:-1]) 
            if msg["role"] == "user"
        ]
        
        # Process the latest message
        result = self.process_message(latest_user_message["content"])
        
        # Merge new response with existing message history
        updated_messages = messages[:-1] + [latest_user_message]
        if result["response"]:
            updated_messages.append({"role": "assistant", "content": result["response"]})
        
        return {
            "response": result["response"],
            "messages": updated_messages,
            "debug_logs": result.get("debug_logs")
        }
        
def create_farm_chat_interface(farm_control_service, model_name="gpt-4o"):
    """Create an enhanced farm chat interface instance."""
    return EnhancedFarmChatInterface(farm_control_service, model_name=model_name)


